#!/usr/bin/env python3
"""Run frozen, deterministic public evaluations for abstraction evidence discovery."""

import argparse
import difflib
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from improvement import tree_identity


SCHEMA_VERSION = "1.0"
EVALUATION_SCOPE = "public-regression"
SKILL_ROOT = Path(__file__).resolve().parents[1]
CASES_DIRECTORY = SKILL_ROOT / "evals" / "cases"
EXPECTED_DIRECTORY = SKILL_ROOT / "evals" / "expected"
MANIFEST_PATH = SKILL_ROOT / "evals" / "manifest.json"
COLLECTOR_PATH = SKILL_ROOT / "scripts" / "collect_evidence.py"
GOVERNANCE_CASE_ID = "governance"
# A path component named `.git` cannot be committed to a git repository: git
# refuses to add it, so a fixture that needs a nested-checkout marker would be
# silently dropped from any clone.  The marker is stored under FIXTURE_MARKER
# and renamed when the case is materialized for a run.
FIXTURE_MARKER = "dot-git"
FIXTURE_MARKER_TARGET = ".git"
GOVERNANCE_RUNNER_PATH = (
    SKILL_ROOT / "evals" / "governance-cases" / "test_governance.py"
)

REQUIRED_IDENTITY_FILES = (
    COLLECTOR_PATH,
    GOVERNANCE_RUNNER_PATH,
    SKILL_ROOT / "scripts" / "improvement.py",
    SKILL_ROOT / "scripts" / "run_eval.py",
    SKILL_ROOT / "scripts" / "validate_findings.py",
    SKILL_ROOT / "evals" / "model-policy.json",
    SKILL_ROOT / "evals" / "rubric.json",
)
REQUIRED_IDENTITY_DIRECTORIES = (
    CASES_DIRECTORY,
    EXPECTED_DIRECTORY,
    SKILL_ROOT / "evals" / "governance-cases",
    SKILL_ROOT / "evals" / "schemas",
)
CASE_INTENT = {
    "anti_abstraction": (
        "Signals must surface, but the fixtures intentionally cross domain or "
        "platform boundaries and are not an extraction recommendation."
    ),
    "shared_candidates": (
        "Signals exercise plausible shared elements that still require contextual "
        "abstraction and safety review."
    ),
    "duplicate_subtree": (
        "A nested worktree checkout marked by a gitdir file must be skipped, so "
        "cross-tree copies of the same files produce no candidates while the "
        "primary tree still scans."
    ),
    "token_block_clones": (
        "Type-2 token-block clones across renamed identifiers must surface as "
        "token_block_clone candidates with deterministic ordering, while short "
        "incidental overlaps below the threshold stay silent."
    ),
    GOVERNANCE_CASE_ID: (
        "Public deterministic regression checks for evaluator governance and "
        "promotion controls."
    ),
}
IDENTITY_MESSAGE = (
    "NEW-EVAL-IDENTITY: frozen evaluator inputs changed. Review the change and "
    "create a new eval identity explicitly before accepting new results."
)
CREATE_IDENTITY_NOTICE = (
    "NEW-EVAL-IDENTITY: this deliberate operation replaces the frozen evaluator "
    "identity. Review every changed input before retaining the new manifest."
)
SCRUBBED_RUNPY_BOOTSTRAP = (
    "import runpy,sys;"
    "module_dir=sys.argv[1];target=sys.argv[2];"
    "sys.path.insert(0,module_dir);"
    "sys.argv=[target]+sys.argv[3:];"
    "runpy.run_path(target,run_name='__main__')"
)


def stable_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def scrubbed_python_environment() -> Dict[str, str]:
    return {
        "LANG": "C",
        "LC_ALL": "C",
        "PATH": os.defpath,
        "PYTHONHASHSEED": "0",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1",
    }


def scrubbed_script_command(path: Path, *arguments: str) -> List[str]:
    return [
        sys.executable,
        "-I",
        "-S",
        "-B",
        "-c",
        SCRUBBED_RUNPY_BOOTSTRAP,
        str(path.parent),
        str(path),
        *arguments,
    ]


def relative_to_skill(path: Path) -> str:
    return path.relative_to(SKILL_ROOT).as_posix()


def required_input_differences() -> List[Dict[str, str]]:
    differences: List[Dict[str, str]] = []
    for path in REQUIRED_IDENTITY_FILES:
        if not path.is_file():
            differences.append(
                {"path": relative_to_skill(path), "reason": "required_input_missing"}
            )
    for directory in REQUIRED_IDENTITY_DIRECTORIES:
        if not directory.is_dir():
            differences.append(
                {
                    "path": relative_to_skill(directory),
                    "reason": "required_input_directory_missing",
                }
            )
            continue
        if not any(path.is_file() for path in directory.rglob("*")):
            differences.append(
                {
                    "path": relative_to_skill(directory),
                    "reason": "required_input_directory_empty",
                }
            )
    # An identity-bearing file whose path contains a `.git` component cannot be
    # committed, so it would vanish from every clone while still being frozen
    # into the manifest.  Refuse to freeze or verify such a tree.
    for path in current_identity_paths():
        name = relative_to_skill(path)
        if any(part == FIXTURE_MARKER_TARGET for part in Path(name).parts):
            differences.append(
                {"path": name, "reason": "path_not_representable_in_git"}
            )
    return sorted(differences, key=lambda item: (item["path"], item["reason"]))


def current_identity_paths() -> List[Path]:
    paths = [path for path in REQUIRED_IDENTITY_FILES if path.is_file()]
    for directory in REQUIRED_IDENTITY_DIRECTORIES:
        if directory.is_dir():
            paths.extend(path for path in directory.rglob("*") if path.is_file())
    unique_paths = {path.resolve(): path for path in paths}
    return sorted(unique_paths.values(), key=relative_to_skill)


def manifest_identity_sha256(manifest: Dict[str, Any]) -> str:
    identity_payload = {
        key: value for key, value in manifest.items() if key != "identity_sha256"
    }
    return sha256_bytes(stable_json_bytes(identity_payload))


def discovery_case_ids() -> List[str]:
    if not CASES_DIRECTORY.is_dir():
        return []
    return sorted(path.name for path in CASES_DIRECTORY.iterdir() if path.is_dir())


def public_case_ids() -> List[str]:
    return sorted(set(discovery_case_ids() + [GOVERNANCE_CASE_ID]))


def build_identity_manifest() -> Dict[str, Any]:
    files = {
        relative_to_skill(path): sha256_file(path) for path in current_identity_paths()
    }
    manifest: Dict[str, Any] = {
        "algorithm": "sha256",
        "case_intent": CASE_INTENT,
        "evaluation_scope": EVALUATION_SCOPE,
        "files": files,
        "notice": CREATE_IDENTITY_NOTICE,
        "public_case_ids": public_case_ids(),
        "schema_version": SCHEMA_VERSION,
    }
    manifest["identity_sha256"] = manifest_identity_sha256(manifest)
    return manifest


def load_manifest() -> Tuple[Optional[Dict[str, Any]], List[Dict[str, str]]]:
    if not MANIFEST_PATH.is_file():
        return None, [{"path": "evals/manifest.json", "reason": "missing_manifest"}]
    try:
        value = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None, [{"path": "evals/manifest.json", "reason": "invalid_manifest"}]
    if not isinstance(value, dict):
        return None, [{"path": "evals/manifest.json", "reason": "invalid_manifest"}]
    return value, []


def verify_frozen_identity() -> Tuple[bool, List[Dict[str, str]], Optional[str]]:
    differences = required_input_differences()
    manifest, manifest_errors = load_manifest()
    differences.extend(manifest_errors)
    if manifest is None:
        return False, differences, None

    if (
        manifest.get("algorithm") != "sha256"
        or manifest.get("schema_version") != SCHEMA_VERSION
    ):
        differences.append(
            {"path": "evals/manifest.json", "reason": "unsupported_manifest_format"}
        )

    declared_identity = manifest.get("identity_sha256")
    computed_identity = manifest_identity_sha256(manifest)
    if (
        not isinstance(declared_identity, str)
        or not re.fullmatch(r"[0-9a-f]{64}", declared_identity)
        or declared_identity != computed_identity
    ):
        differences.append(
            {"path": "evals/manifest.json", "reason": "manifest_identity_mismatch"}
        )

    expected_files = manifest.get("files")
    if not isinstance(expected_files, dict):
        differences.append(
            {"path": "evals/manifest.json", "reason": "missing_file_hashes"}
        )
        return False, differences, declared_identity if isinstance(declared_identity, str) else None

    declared_public_case_ids = manifest.get("public_case_ids")
    if (
        not isinstance(declared_public_case_ids, list)
        or not declared_public_case_ids
        or not all(isinstance(item, str) and item for item in declared_public_case_ids)
        or declared_public_case_ids != sorted(set(declared_public_case_ids))
    ):
        differences.append(
            {"path": "evals/manifest.json", "reason": "invalid_public_case_ids"}
        )
    elif declared_public_case_ids != public_case_ids():
        differences.append(
            {"path": "evals/manifest.json", "reason": "public_case_ids_mismatch"}
        )

    declared_case_intent = manifest.get("case_intent")
    if not isinstance(declared_case_intent, dict) or set(declared_case_intent) != set(
        public_case_ids()
    ):
        differences.append(
            {"path": "evals/manifest.json", "reason": "case_intent_mismatch"}
        )

    invalid_hash_paths = sorted(
        name
        for name, value in expected_files.items()
        if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value)
    )
    for name in invalid_hash_paths:
        differences.append({"path": name, "reason": "invalid_file_hash"})

    actual_paths = current_identity_paths()
    actual_names = {relative_to_skill(path) for path in actual_paths}
    expected_names = set(expected_files)
    for name in sorted(expected_names - actual_names):
        differences.append({"path": name, "reason": "missing_file"})
    for name in sorted(actual_names - expected_names):
        differences.append({"path": name, "reason": "unfrozen_file"})
    for path in actual_paths:
        name = relative_to_skill(path)
        expected_hash = expected_files.get(name)
        if expected_hash is None:
            continue
        actual_hash = sha256_file(path)
        if actual_hash != expected_hash:
            differences.append(
                {
                    "actual_sha256": actual_hash,
                    "expected_sha256": str(expected_hash),
                    "path": name,
                    "reason": "hash_mismatch",
                }
            )

    differences.sort(key=lambda item: (item["path"], item["reason"]))
    identity = declared_identity if isinstance(declared_identity, str) else None
    return not differences, differences, identity


def create_new_eval_identity(acknowledged: bool) -> int:
    if not acknowledged:
        result = {
            "evaluation_scope": EVALUATION_SCOPE,
            "notice": CREATE_IDENTITY_NOTICE,
            "operation": "create-new-eval-identity",
            "required_acknowledgement": "--acknowledge-new-eval-identity",
            "schema_version": SCHEMA_VERSION,
            "status": "refused",
        }
        sys.stdout.buffer.write(stable_json_bytes(result))
        return 2

    differences = required_input_differences()
    undescribed_cases = sorted(set(public_case_ids()) - set(CASE_INTENT))
    for case_name in undescribed_cases:
        differences.append(
            {"path": "evals/cases/" + case_name, "reason": "case_intent_missing"}
        )
    stale_intents = sorted(set(CASE_INTENT) - set(public_case_ids()))
    for case_name in stale_intents:
        differences.append(
            {"path": "evals/cases/" + case_name, "reason": "case_intent_stale"}
        )
    if differences:
        result = {
            "differences": differences,
            "evaluation_scope": EVALUATION_SCOPE,
            "notice": CREATE_IDENTITY_NOTICE,
            "operation": "create-new-eval-identity",
            "schema_version": SCHEMA_VERSION,
            "status": "failed",
        }
        sys.stdout.buffer.write(stable_json_bytes(result))
        return 1

    preflight_cases = [evaluate_case(case_id) for case_id in public_case_ids()]
    if not preflight_cases or any(
        case["status"] != "passed" for case in preflight_cases
    ):
        result = {
            "cases": preflight_cases,
            "evaluation_scope": EVALUATION_SCOPE,
            "notice": CREATE_IDENTITY_NOTICE,
            "operation": "create-new-eval-identity",
            "schema_version": SCHEMA_VERSION,
            "status": "failed",
        }
        sys.stdout.buffer.write(stable_json_bytes(result))
        return 1

    manifest = build_identity_manifest()
    payload = stable_json_bytes(manifest)
    temporary_path = MANIFEST_PATH.with_name(MANIFEST_PATH.name + ".tmp")
    temporary_path.write_bytes(payload)
    os.replace(str(temporary_path), str(MANIFEST_PATH))
    result = {
        "evaluation_scope": EVALUATION_SCOPE,
        "file_count": len(manifest["files"]),
        "identity_sha256": manifest["identity_sha256"],
        "notice": CREATE_IDENTITY_NOTICE,
        "operation": "create-new-eval-identity",
        "preflight_cases": preflight_cases,
        "public_case_ids": manifest["public_case_ids"],
        "schema_version": SCHEMA_VERSION,
        "status": "created",
    }
    sys.stdout.buffer.write(stable_json_bytes(result))
    return 0


def materialize_case(case_name: str, destination_parent: Path) -> Path:
    """Copy one case under `destination_parent`, renaming fixture markers.

    The copy keeps the case's own directory name, and the scanner emits only
    root-relative paths plus the root's basename, so a case run from a
    materialized copy produces byte-identical output no matter where the copy
    lives.  Each run therefore also uses a different absolute path, which makes
    the two-run byte-identity check a stricter test than it was when both runs
    shared one path.
    """

    destination = destination_parent / case_name
    shutil.copytree(CASES_DIRECTORY / case_name, destination, symlinks=True)
    markers = sorted(
        destination.rglob(FIXTURE_MARKER), key=lambda item: item.as_posix()
    )
    for marker in markers:
        marker.rename(marker.with_name(FIXTURE_MARKER_TARGET))
    return destination


def run_collector(case_name: str) -> subprocess.CompletedProcess:
    with tempfile.TemporaryDirectory(prefix="abstraction-police-case-") as raw:
        case_path = materialize_case(case_name, Path(raw))
        return subprocess.run(
            scrubbed_script_command(COLLECTOR_PATH, str(case_path)),
            cwd=str(SKILL_ROOT.parent),
            env=scrubbed_python_environment(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )


def run_governance() -> subprocess.CompletedProcess:
    return subprocess.run(
        scrubbed_script_command(GOVERNANCE_RUNNER_PATH),
        cwd=str(SKILL_ROOT.parent),
        env=scrubbed_python_environment(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def emit_diff(case_name: str, expected: bytes, actual: bytes) -> None:
    expected_lines = expected.decode("utf-8", errors="replace").splitlines(keepends=True)
    actual_lines = actual.decode("utf-8", errors="replace").splitlines(keepends=True)
    diff = difflib.unified_diff(
        expected_lines,
        actual_lines,
        fromfile="evals/expected/" + case_name + ".json",
        tofile="actual/" + case_name + ".json",
    )
    sys.stderr.writelines(diff)


def evaluate_discovery_case(case_name: str) -> Dict[str, Any]:
    expected_path = EXPECTED_DIRECTORY / (case_name + ".json")
    first = run_collector(case_name)
    second = run_collector(case_name)
    byte_identical = (
        first.returncode == 0
        and second.returncode == 0
        and first.stdout == second.stdout
        and first.stderr == second.stderr
    )
    expected_exists = expected_path.is_file()
    expected = expected_path.read_bytes() if expected_exists else b""
    expected_match = first.returncode == 0 and expected_exists and first.stdout == expected
    stderr_empty = not first.stderr and not second.stderr
    passed = byte_identical and expected_match and stderr_empty

    if expected_exists and first.returncode == 0 and not expected_match:
        emit_diff(case_name, expected, first.stdout)
    if first.stderr:
        sys.stderr.buffer.write(first.stderr)
    if second.stderr and second.stderr != first.stderr:
        sys.stderr.buffer.write(second.stderr)

    return {
        "byte_identical": byte_identical,
        "expected_match": expected_match,
        "name": case_name,
        "status": "passed" if passed else "failed",
        "stderr_empty": stderr_empty,
    }


def evaluate_governance_case() -> Dict[str, Any]:
    expected_path = EXPECTED_DIRECTORY / (GOVERNANCE_CASE_ID + ".json")
    first = run_governance()
    second = run_governance()
    byte_identical = (
        first.returncode == 0
        and second.returncode == 0
        and first.stdout == second.stdout
        and first.stderr == second.stderr
    )
    expected_exists = expected_path.is_file()
    expected = expected_path.read_bytes() if expected_exists else b""
    try:
        parsed = json.loads(first.stdout)
    except (json.JSONDecodeError, UnicodeDecodeError):
        parsed = None
    governance_passed = isinstance(parsed, dict) and parsed.get("status") == "passed"
    expected_match = (
        first.returncode == 0
        and expected_exists
        and first.stdout == expected
        and governance_passed
    )
    stderr_empty = not first.stderr and not second.stderr
    passed = byte_identical and expected_match and stderr_empty

    if expected_exists and first.returncode == 0 and first.stdout != expected:
        emit_diff(GOVERNANCE_CASE_ID, expected, first.stdout)
    if first.stderr:
        sys.stderr.buffer.write(first.stderr)
    if second.stderr and second.stderr != first.stderr:
        sys.stderr.buffer.write(second.stderr)

    return {
        "byte_identical": byte_identical,
        "expected_match": expected_match,
        "name": GOVERNANCE_CASE_ID,
        "status": "passed" if passed else "failed",
        "stderr_empty": stderr_empty,
    }


def evaluate_case(case_name: str) -> Dict[str, Any]:
    if case_name == GOVERNANCE_CASE_ID:
        return evaluate_governance_case()
    return evaluate_discovery_case(case_name)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run frozen exact-output evaluations, or deliberately create a new "
            "eval identity as a separate operation."
        )
    )
    parser.add_argument(
        "operation",
        choices=("run", "create-new-eval-identity"),
        default="run",
        nargs="?",
    )
    parser.add_argument(
        "--case",
        action="append",
        dest="cases",
        help="Run one named public case. Repeat to select multiple cases.",
    )
    parser.add_argument(
        "--acknowledge-new-eval-identity",
        action="store_true",
        help="Required acknowledgement for the create-new-eval-identity operation.",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if args.operation == "create-new-eval-identity":
        if args.cases:
            print("error: --case cannot be used while creating an eval identity", file=sys.stderr)
            return 2
        return create_new_eval_identity(args.acknowledge_new_eval_identity)
    if args.acknowledge_new_eval_identity:
        print(
            "error: acknowledgement is valid only for create-new-eval-identity",
            file=sys.stderr,
        )
        return 2

    identity_ok, identity_differences, identity_sha256 = verify_frozen_identity()
    if not identity_ok:
        print(IDENTITY_MESSAGE, file=sys.stderr)
        identity_result: Dict[str, Any] = {
            "differences": identity_differences,
            "status": "failed",
        }
        if identity_sha256 is not None:
            identity_result["sha256"] = identity_sha256
        result = {
            "cases": [],
            "evaluation_scope": EVALUATION_SCOPE,
            "identity": identity_result,
            "schema_version": SCHEMA_VERSION,
            "status": "failed",
        }
        sys.stdout.buffer.write(stable_json_bytes(result))
        return 1

    known_cases = public_case_ids()
    selected_cases = sorted(set(args.cases)) if args.cases else known_cases
    unknown_cases = sorted(set(selected_cases) - set(known_cases))
    identity_result = {
        "file_count": len(current_identity_paths()),
        "sha256": identity_sha256,
        "status": "passed",
    }
    if unknown_cases:
        result = {
            "cases": [],
            "evaluation_scope": EVALUATION_SCOPE,
            "identity": identity_result,
            "schema_version": SCHEMA_VERSION,
            "status": "failed",
            "unknown_cases": unknown_cases,
        }
        sys.stdout.buffer.write(stable_json_bytes(result))
        return 2

    subject_before = tree_identity(SKILL_ROOT)
    case_results = [evaluate_case(case_name) for case_name in selected_cases]
    subject_after = tree_identity(SKILL_ROOT)
    subject_stable = subject_before == subject_after
    passed = (
        bool(case_results)
        and subject_stable
        and all(result["status"] == "passed" for result in case_results)
    )
    result = {
        "cases": case_results,
        "evaluation_scope": EVALUATION_SCOPE,
        "identity": identity_result,
        "schema_version": SCHEMA_VERSION,
        "status": "passed" if passed else "failed",
        "subject": {
            "file_count": subject_before["file_count"],
            "sha256": subject_before["sha256"],
            "status": "passed" if subject_stable else "failed",
        },
    }
    sys.stdout.buffer.write(stable_json_bytes(result))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
