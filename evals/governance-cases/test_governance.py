#!/usr/bin/env python3
"""Deterministic public regression checks for improvement governance."""

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Mapping


SKILL_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = SKILL_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import collect_evidence  # noqa: E402
import improvement  # noqa: E402
import run_eval  # noqa: E402
from improvement import IGNORED_TREE_DIRS, IGNORED_TREE_FILES  # noqa: E402
from validate_findings import FindingsValidationError, validate_document  # noqa: E402


MODEL_FIELDS = [
    "provider",
    "model_id",
    "model_revision",
    "backend_fingerprint",
    "reasoning_effort",
    "temperature",
    "seed",
    "toolset_hash",
    "system_prompt_hash",
    "skill_hash",
    "eval_manifest_hash",
    "input_corpus_hash",
]

MINIMAL_RUNNER = r'''#!/usr/bin/env python3
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IGNORED_DIRS = {".git", "__pycache__"}
IGNORED_FILES = {".DS_Store"}

def stable(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")

def file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def tree_identity():
    records = []
    for path in sorted(ROOT.rglob("*"), key=lambda item: item.as_posix()):
        relative = path.relative_to(ROOT)
        if any(part in IGNORED_DIRS for part in relative.parts):
            continue
        if path.name in IGNORED_FILES:
            continue
        if path.is_symlink():
            raise RuntimeError("symlink refused")
        if path.is_file():
            records.append((relative.as_posix(), file_hash(path)))
    digest = hashlib.sha256()
    for name, value in records:
        digest.update(name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(value.encode("ascii"))
        digest.update(b"\n")
    return {"file_count": len(records), "sha256": digest.hexdigest()}

def main():
    manifest_path = ROOT / "evals" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload = {key: value for key, value in manifest.items() if key != "identity_sha256"}
    identity = hashlib.sha256(stable(payload)).hexdigest()
    if identity != manifest.get("identity_sha256"):
        return 1
    for name, expected in manifest["files"].items():
        if file_hash(ROOT / name) != expected:
            return 1
    case_ids = manifest["public_case_ids"]
    result = {
        "cases": [
            {
                "byte_identical": True,
                "expected_match": True,
                "name": name,
                "status": "passed",
                "stderr_empty": True,
            }
            for name in case_ids
        ],
        "evaluation_scope": "public-regression",
        "identity": {
            "file_count": len(manifest["files"]),
            "sha256": identity,
            "status": "passed",
        },
        "schema_version": "1.0",
        "status": "passed",
        "subject": dict(tree_identity(), status="passed"),
    }
    sys.stdout.buffer.write(stable(result))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
'''


def stable_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )


def compact_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(stable_bytes(value))


def manifest_document(root: Path) -> Dict[str, Any]:
    identity_paths: List[Path] = []
    for relative in improvement.EVAL_IDENTITY_FILES:
        identity_paths.append(root / relative)
    for relative in (
        improvement.EVAL_IDENTITY_DIRECTORIES
        + improvement.OPTIONAL_EVAL_IDENTITY_DIRECTORIES
    ):
        directory = root / relative
        if directory.is_dir():
            identity_paths.extend(item for item in directory.rglob("*") if item.is_file())
    unique_paths = sorted(set(identity_paths), key=lambda item: item.as_posix())
    payload: Dict[str, Any] = {
        "algorithm": "sha256",
        "evaluation_scope": "public-regression",
        "files": {
            item.relative_to(root).as_posix(): hashlib.sha256(item.read_bytes()).hexdigest()
            for item in unique_paths
        },
        "notice": "public governance fixture",
        "public_case_ids": ["governance", "public-fixture"],
        "schema_version": "1.0",
    }
    payload["identity_sha256"] = hashlib.sha256(stable_bytes(payload)).hexdigest()
    return payload


def make_skill(root: Path, candidate: bool = False) -> Dict[str, Any]:
    (root / "scripts").mkdir(parents=True)
    (root / "evals" / "cases" / "public-fixture").mkdir(parents=True)
    (root / "references").mkdir(parents=True)
    (root / "agents").mkdir(parents=True)
    (root / "SKILL.md").write_text(
        "# Fixture skill\n\nCandidate instruction.\n"
        if candidate
        else "# Fixture skill\n\nLive instruction.\n",
        encoding="utf-8",
    )
    (root / "references" / "rules.md").write_text("Fixture rules.\n", encoding="utf-8")
    (root / "agents" / "openai.yaml").write_text("name: fixture\n", encoding="utf-8")
    (root / "scripts" / "collect_evidence.py").write_text(
        "#!/usr/bin/env python3\nprint('fixture')\n", encoding="utf-8"
    )
    (root / "scripts" / "run_eval.py").write_text(MINIMAL_RUNNER, encoding="utf-8")
    for name in ("improvement.py", "validate_findings.py"):
        (root / "scripts" / name).write_text("# evaluator fixture\n", encoding="utf-8")
    (root / "evals" / "cases" / "public-fixture" / "input.txt").write_text(
        "fixture\n", encoding="utf-8"
    )
    write_json(
        root / "evals" / "model-policy.json",
        {"schema_version": "1.0", "comparison_key_fields": MODEL_FIELDS},
    )
    write_json(root / "evals" / "rubric.json", {"schema_version": "1.0"})
    write_json(root / "evals" / "expected" / "public-fixture.json", {"fixture": True})
    write_json(root / "evals" / "schemas" / "fixture.schema.json", {"type": "object"})
    (root / "evals" / "governance-cases").mkdir(parents=True)
    (root / "evals" / "governance-cases" / "fixture.txt").write_text(
        "public governance fixture\n", encoding="utf-8"
    )
    manifest = manifest_document(root)
    write_json(root / "evals" / "manifest.json", manifest)
    return manifest


def public_result(root: Path) -> Dict[str, Any]:
    command = [sys.executable, "-B", str(root / "scripts" / "run_eval.py")]
    first = subprocess.run(command, cwd=str(root), capture_output=True, check=False)
    second = subprocess.run(command, cwd=str(root), capture_output=True, check=False)
    if (
        first.returncode != 0
        or second.returncode != 0
        or first.stderr
        or second.stderr
        or first.stdout != second.stdout
    ):
        raise AssertionError("fixture public evaluator was not deterministic and successful")
    value = json.loads(first.stdout)
    if value.get("status") != "passed":
        raise AssertionError("fixture public evaluator did not pass")
    return value


def holdout_result(
    root: Path,
    manifest: Mapping[str, Any],
    *,
    external_identity: str = "1" * 64,
    failures: List[str] = None,
) -> Dict[str, Any]:
    failure_items = list(failures or [])
    return {
        "candidate_access_ended": True,
        "case_ids": ["external-hidden-a"],
        "deterministic": True,
        "eval_manifest_identity": manifest["identity_sha256"],
        "external_suite_identity": external_identity,
        "failures": failure_items,
        "grader_id": "independent-grader",
        "grader_owned": True,
        "input_corpus_hash": "3" * 64,
        "model_intrinsic_key": improvement.NOT_APPLICABLE,
        "regressions": 0,
        "schema_version": "1.0",
        "sealed": True,
        "status": "passed",
        "subject_sha256": improvement.hash_tree(root),
        "suite": "holdout",
        "tests_discovered": 1,
        "tests_failed": 0,
        "tests_passed": 1,
    }


def run_args(
    root: Path,
    out: Path,
    public_path: Path,
    holdout_path: Path,
    baseline: Path = None,
) -> argparse.Namespace:
    return argparse.Namespace(
        baseline_receipt=baseline,
        eval_manifest=root / "evals" / "manifest.json",
        manifest_change_reason=None,
        model_change_reason=None,
        model_config=None,
        model_id=None,
        model_independent=True,
        model_policy=root / "evals" / "model-policy.json",
        model_record=None,
        out_dir=out,
        producer_id="candidate-producer",
        result=[f"public={public_path}", f"holdout={holdout_path}"],
        scanner_change_reason=None,
        scanner_version="1.0",
        skill_root=root,
    )


def assert_schema_shape(document: Mapping[str, Any], schema: Mapping[str, Any]) -> None:
    required = set(schema.get("required", []))
    missing = required - set(document)
    if missing:
        raise AssertionError(f"schema-required keys missing from emitted object: {sorted(missing)}")
    if schema.get("additionalProperties") is False:
        extras = set(document) - set(schema.get("properties", {}))
        if extras:
            raise AssertionError(f"emitted keys absent from schema: {sorted(extras)}")
    if json.loads(compact_bytes(document).decode("utf-8")) != document:
        raise AssertionError("canonical JSON round trip changed the emitted object")


def load_schema(name: str) -> Dict[str, Any]:
    return json.loads(
        (SKILL_ROOT / "evals" / "schemas" / name).read_text(encoding="utf-8")
    )


def approval_payload(
    base: Mapping[str, Any],
    candidate: Mapping[str, Any],
    public: Mapping[str, Any],
    holdout: Mapping[str, Any],
) -> Dict[str, Any]:
    public_summary = improvement.summarize_result(
        public,
        "public",
        expected_public_identity=public["identity"]["sha256"],
        expected_public_case_ids=["governance", "public-fixture"],
        expected_subject_hash=candidate["skill_hash"],
    )
    holdout_summary = improvement.summarize_result(
        holdout,
        "holdout",
        expected_public_identity=public["identity"]["sha256"],
        expected_subject_hash=candidate["skill_hash"],
        expected_holdout_model_key=improvement.NOT_APPLICABLE,
    )
    return {
        "approval_kind": "explicit-human",
        "approved": True,
        "approved_at": "2026-08-06T12:00:00-04:00",
        "approval_statement": "I reviewed and approve this exact candidate evidence.",
        "approver_id": "authorized-approver",
        "base_receipt_id": base["receipt_id"],
        "candidate_identity": candidate["skill_identity"],
        "candidate_receipt_id": candidate["receipt_id"],
        "candidate_skill_hash": candidate["skill_hash"],
        "eval_manifest_hash": candidate["eval_manifest_hash"],
        "external_suite_identity": holdout_summary["external_suite_identity"],
        "grader_id": "independent-grader",
        "holdout_result_hash": holdout_summary["result_hash"],
        "manifest_change_approved": False,
        "model_change_approved": False,
        "model_comparison_key": candidate["model"]["comparison_key"],
        "model_policy_hash": candidate["model"]["model_policy_hash"],
        "public_result_hash": public_summary["result_hash"],
        "public_suite_identity": public_summary["public_suite_identity"],
        "scanner_change_approved": False,
        "schema_version": "1.0",
    }


def expect_governance_error(function: Any, contains: str) -> None:
    try:
        function()
    except improvement.GovernanceError as exc:
        if contains not in str(exc):
            raise AssertionError(f"expected error containing {contains!r}, got {exc!r}")
    else:
        raise AssertionError(f"expected GovernanceError containing {contains!r}")


def expect_findings_error(function: Any, contains: str) -> None:
    try:
        function()
    except FindingsValidationError as exc:
        if contains not in str(exc):
            raise AssertionError(f"expected findings error containing {contains!r}, got {exc!r}")
    else:
        raise AssertionError(f"expected FindingsValidationError containing {contains!r}")


def zero_findings_document(audit_root: Path, skill_root: Path, limited: bool) -> Dict[str, Any]:
    limitations = (
        {"mode": "specified", "items": ["Audit stopped before semantic review."]}
        if limited
        else {"mode": "none", "items": []}
    )
    scanner = skill_root / "scripts" / "collect_evidence.py"
    output_directory = audit_root / "audit-output"
    output_directory.mkdir(exist_ok=True)
    return {
        "audit": {
            "commands": ["python3 collect_evidence.py ."],
            "date": "2026-08-06",
            "dirty_state": "clean",
            "revision": "fixture-revision",
            "root": str(audit_root.resolve()),
        },
        "execution": {
            "commands": ["python3 collect_evidence.py ."],
            "output_directory": str(output_directory.resolve()),
            "requested_exclusions": {"mode": "none", "items": []},
            "scanner": {
                "options": [],
                "sha256": hashlib.sha256(scanner.read_bytes()).hexdigest(),
                "stderr": {"content": "", "status": "empty"},
                "version": "1.0",
            },
        },
        "findings": [],
        "limitations": limitations,
        "schema_version": "1.0",
        "scope": "Fixture audit",
        "summary": {
            "triage": {
                "candidates_by_kind": {},
                "candidates_total": 0,
                "dropped_by_class": {},
                "investigated": 0,
                "not_reached": 0,
                "promoted": 0,
            }
        },
    }


def authority_negative_document(audit_root: Path, skill_root: Path) -> Dict[str, Any]:
    first = audit_root / "first.py"
    second = audit_root / "second.py"
    first.write_text("TOKEN = 'blue'\n", encoding="utf-8")
    second.write_text("TOKEN = 'blue'\n", encoding="utf-8")
    document = zero_findings_document(audit_root, skill_root, limited=False)
    document["summary"]["triage"] = {
        "candidates_by_kind": {"repeated_literal": 1},
        "candidates_total": 1,
        "dropped_by_class": {},
        "investigated": 1,
        "not_reached": 0,
        "promoted": 1,
    }
    source_one = {"path": str(first.resolve())}
    source_two = {"path": str(second.resolve())}
    evidence = {
        "detail": "The design team maintains both values.",
        "id": "E1",
        "limitations": {"mode": "none", "items": []},
        "provenance": {
            "kind": "direct-inspection",
            "method": "Read both files.",
            "producer": "fixture-reviewer",
        },
        "sources": [source_one, source_two],
        "type": "boundary-analysis",
    }
    gate = {
        "evidence_refs": ["E1"],
        "rationale": "Fixture rationale.",
        "status": "pass",
    }
    document["findings"] = [
        {
            "affected_consumers": [],
            "artifact_class": "design-token",
            "assumptions": [],
            "boundary_constraints": [],
            "change_risk": {"level": "low", "rationale": "Fixture."},
            "claim": "The token definitions overlap semantically.",
            "claim_level": "semantic-overlap",
            "confidence": "probable",
            "disposition": "generate",
            "evidence": [evidence],
            "exclusions": [],
            "id": "AP-002",
            "locations": [source_one, source_two],
            "maintenance_risk": {"level": "medium", "rationale": "Fixture."},
            "meaningful_differences": [],
            "missing_evidence": [],
            "observations": [
                {
                    "command": "read files",
                    "detail": "Both files contain a token.",
                    "sources": [source_one, source_two],
                }
            ],
            "owners": ["design-team"],
            "public_boundaries": [],
            "recommendation": "Generate both values from JSON.",
            "rollback": {
                "boundary": "Token build.",
                "steps": ["Restore files."],
                "trigger": "Parity failure.",
            },
            "severity": "medium",
            "squint": {letter: dict(gate) for letter in ("S", "Q", "U", "I", "N", "T")},
            "verification_plan": {
                "steps": [
                    {
                        "command": "python3 verify.py",
                        "environment": "fixture",
                        "expected": "passes",
                        "failure_means": "generation differs",
                        "fixtures": [],
                        "prerequisites": [],
                    }
                ],
                "unrun_checks": [],
            },
        }
    ]
    return document


def run_checks() -> List[str]:
    checks: List[str] = []
    with tempfile.TemporaryDirectory(prefix="abstraction-police-governance-") as raw:
        root = Path(raw)
        live = root / "live"
        candidate_root = root / "candidate"
        live_manifest = make_skill(live)
        candidate_manifest = make_skill(candidate_root, candidate=True)

        live_public = public_result(live)
        candidate_public = public_result(candidate_root)
        live_holdout = holdout_result(live, live_manifest)
        candidate_holdout = holdout_result(candidate_root, candidate_manifest)
        live_public_path = root / "live-public.json"
        candidate_public_path = root / "candidate-public.json"
        live_holdout_path = root / "live-holdout.json"
        candidate_holdout_path = root / "candidate-holdout.json"
        write_json(live_public_path, live_public)
        write_json(candidate_public_path, candidate_public)
        write_json(live_holdout_path, live_holdout)
        write_json(candidate_holdout_path, candidate_holdout)

        base_path = improvement.record_run(
            run_args(live, root / "base-receipts", live_public_path, live_holdout_path)
        )
        candidate_path = improvement.record_run(
            run_args(
                candidate_root,
                root / "candidate-receipts",
                candidate_public_path,
                candidate_holdout_path,
                base_path,
            )
        )
        base = improvement._load_json(base_path)
        candidate = improvement._load_json(candidate_path)

        approval, approval_path = improvement._seal_json(
            approval_payload(base, candidate, candidate_public, candidate_holdout),
            id_field="approval_id",
            id_prefix="approval",
            filename_prefix="approval",
            out_dir=root / "approval",
        )
        gate_path, eligible = improvement.gate(
            argparse.Namespace(
                approval_receipt=approval_path,
                base_receipt=base_path,
                candidate_receipt=candidate_path,
                candidate_skill_root=candidate_root,
                grader_id="independent-grader",
                holdout_result=candidate_holdout_path,
                live_skill_root=live,
                out_dir=root / "gate",
                public_result=candidate_public_path,
            )
        )
        if not eligible:
            raise AssertionError("valid independently graded evidence was not eligible")
        gate = improvement._load_json(gate_path)
        gate_checks = {item["name"]: item["passed"] for item in gate["checks"]}
        if not gate_checks.get("trusted-live-public-rerun") or not gate_checks.get(
            "trusted-candidate-public-rerun"
        ):
            raise AssertionError("promotion gate did not trust-rerun both evaluators")
        checks.append("subject-bound-trusted-promotion-round-trip")

        schemas = {
            "approval": (approval, load_schema("approval-receipt.schema.json")),
            "promotion": (gate, load_schema("promotion-receipt.schema.json")),
            "run": (candidate, load_schema("run-receipt.schema.json")),
        }
        for document, schema in schemas.values():
            assert_schema_shape(document, schema)
        run_schema = schemas["run"][1]
        assert_schema_shape(candidate["model"], run_schema["$defs"]["model"])
        for result in candidate["results"]:
            assert_schema_shape(result, run_schema["$defs"]["result_summary"])
        evaluation_schema = load_schema("evaluation-result.schema.json")
        assert_schema_shape(candidate_public, evaluation_schema["$defs"]["public_result"])
        assert_schema_shape(candidate_holdout, evaluation_schema["$defs"]["external_holdout_result"])
        checks.append("script-schema-round-trip")

        replay_args = run_args(
            candidate_root,
            root / "replay-receipts",
            live_public_path,
            candidate_holdout_path,
            base_path,
        )
        expect_governance_error(
            lambda: improvement.record_run(replay_args),
            "subject.sha256 does not match",
        )
        checks.append("instruction-only-drift-rejects-replayed-public-result")

        subset = dict(candidate_public)
        subset["cases"] = list(candidate_public["cases"][:-1])
        expect_governance_error(
            lambda: improvement.summarize_result(
                subset,
                "public",
                expected_public_identity=candidate_manifest["identity_sha256"],
                expected_public_case_ids=["governance", "public-fixture"],
                expected_subject_hash=improvement.hash_tree(candidate_root),
            ),
            "exact full case set",
        )
        checks.append("public-subset-cannot-promote")

        catastrophic = holdout_result(
            candidate_root,
            candidate_manifest,
            failures=["catastrophic"],
        )
        expect_governance_error(
            lambda: improvement.summarize_result(catastrophic, "holdout"),
            "empty failures",
        )
        checks.append("passed-holdout-cannot-carry-failures")

        missing_identity = dict(candidate_holdout)
        del missing_identity["external_suite_identity"]
        expect_governance_error(
            lambda: improvement.summarize_result(missing_identity, "holdout"),
            "external_suite_identity",
        )
        checks.append("external-holdout-identity-is-required")

        model_policy, model_policy_hash = improvement._load_model_policy(
            live / "evals" / "model-policy.json"
        )
        alias_record = root / "alias-model.json"
        write_json(
            alias_record,
            {
                "backend_fingerprint": "backend-123",
                "config": {"temperature": 0},
                "input_corpus_hash": "4" * 64,
                "mode": "model-assisted",
                "model_id": "example-model-1",
                "model_revision": "latest",
                "provider": "example-provider",
                "reasoning_effort": "high",
                "seed": 7,
                "system_prompt_hash": "5" * 64,
                "temperature": 0,
                "toolset_hash": "6" * 64,
            },
        )
        expect_governance_error(
            lambda: improvement._model_record(
                model_policy=model_policy,
                model_policy_hash=model_policy_hash,
                model_record_path=alias_record,
                model_independent=False,
                model_id=None,
                model_config=None,
                skill_hash=improvement.hash_tree(live),
                eval_manifest_hash=improvement._json_file_hash(
                    live / "evals" / "manifest.json"
                )[1],
            ),
            "moving alias",
        )
        checks.append("assisted-model-moving-alias-is-rejected")

        audit_root = root / "audited-repo"
        audit_root.mkdir()
        raw_evidence_path = root / "raw-evidence.json"
        write_json(raw_evidence_path, {"candidates": [], "status": "completed"})
        zero_findings = zero_findings_document(audit_root, live, limited=False)
        zero_findings_path = root / "zero-findings.json"
        write_json(zero_findings_path, zero_findings)
        learning_path = improvement.record_audit(
            argparse.Namespace(
                dispositions=None,
                evidence=raw_evidence_path,
                failures=None,
                findings=zero_findings_path,
                outcome="completed",
                out_dir=root / "learning-zero",
                producer_id="audit-producer",
                skill_root=live,
            )
        )
        learning = improvement._load_json(learning_path)
        if learning["improvement_triggers"] or learning["candidate_authority"]:
            raise AssertionError("zero-finding learning receipt gained candidate authority")
        expect_governance_error(
            lambda: improvement.propose(
                argparse.Namespace(
                    candidate_patch=None,
                    dispositions=None,
                    failures=None,
                    findings=None,
                    learning_receipt=learning_path,
                    model_config=None,
                    model_id=None,
                    out_dir=root / "zero-proposal",
                    producer_id="candidate-producer",
                    skill_root=live,
                )
            ),
            "no evaluation failure",
        )
        checks.append("zero-finding-audit-records-learning-without-self-authorization")

        limited_findings = zero_findings_document(audit_root, live, limited=True)
        limited_path = root / "limited-findings.json"
        write_json(limited_path, limited_findings)
        failure_path = root / "failure.json"
        write_json(failure_path, {"failures": ["fixture failure"], "status": "failed"})
        triggered_learning_path = improvement.record_audit(
            argparse.Namespace(
                dispositions=None,
                evidence=raw_evidence_path,
                failures=failure_path,
                findings=limited_path,
                outcome="failed",
                out_dir=root / "learning-failed",
                producer_id="audit-producer",
                skill_root=live,
            )
        )
        request_path = improvement.propose(
            argparse.Namespace(
                candidate_patch=None,
                dispositions=None,
                failures=None,
                findings=None,
                learning_receipt=triggered_learning_path,
                model_config=None,
                model_id=None,
                out_dir=root / "triggered-proposal",
                producer_id="candidate-producer",
                skill_root=live,
            )
        )
        request = improvement._load_json(request_path)
        if not any(item["kind"] == "learning-receipt" for item in request["inputs"]):
            raise AssertionError("proposal did not archive its authorized learning receipt")
        learning_schema = load_schema("audit-learning-receipt.schema.json")
        assert_schema_shape(
            improvement._load_json(triggered_learning_path),
            learning_schema,
        )
        checks.append("failed-audit-learning-can-request-but-not-authorize-candidate")

        authority_negative = authority_negative_document(audit_root, live)
        expect_findings_error(
            lambda: validate_document(
                authority_negative,
                repo_root=audit_root,
                require_existing_paths=True,
            ),
            "typed, cited authority-rule",
        )
        checks.append("ownership-alone-cannot-authorize-generation")

        fabricated = authority_negative_document(audit_root, live)
        fabricated["findings"][0]["locations"][0]["path"] = str(
            (audit_root / "missing.py").resolve()
        )
        expect_findings_error(
            lambda: validate_document(
                fabricated,
                repo_root=audit_root,
                require_existing_paths=True,
            ),
            "does not exist",
        )
        checks.append("fabricated-findings-path-is-rejected")

        tampered = root / "tampered-candidate"
        shutil.copytree(candidate_root, tampered)
        outside_marker = root / "candidate-runner-was-executed.txt"
        marker_statement = (
            f"Path({str(outside_marker)!r}).write_text('executed\\n', encoding='utf-8')"
        )
        runner_path = tampered / "scripts" / "run_eval.py"
        runner_text = runner_path.read_text(encoding="utf-8")
        runner_path.write_text(
            runner_text.replace(
                "\nif __name__ == \"__main__\":",
                f"\n{marker_statement}\n\nif __name__ == \"__main__\":",
                1,
            ),
            encoding="utf-8",
        )
        (tampered / "scripts" / "sitecustomize.py").write_text(
            "from pathlib import Path\n" + marker_statement + "\n",
            encoding="utf-8",
        )
        (tampered / "evals" / "governance-cases" / "json.py").write_text(
            "from pathlib import Path\n" + marker_statement + "\n",
            encoding="utf-8",
        )
        tampered_manifest = manifest_document(tampered)
        write_json(tampered / "evals" / "manifest.json", tampered_manifest)
        tampered_subject = improvement.tree_identity(tampered)
        forged_public = json.loads(json.dumps(candidate_public))
        forged_public["identity"]["sha256"] = tampered_manifest["identity_sha256"]
        forged_public["identity"]["file_count"] = len(tampered_manifest["files"])
        forged_public["subject"] = dict(tampered_subject, status="passed")
        forged_holdout = dict(candidate_holdout)
        forged_holdout["eval_manifest_identity"] = tampered_manifest["identity_sha256"]
        forged_holdout["subject_sha256"] = tampered_subject["sha256"]
        forged_public_path = root / "tampered-public.json"
        forged_holdout_path = root / "tampered-holdout.json"
        write_json(forged_public_path, forged_public)
        write_json(forged_holdout_path, forged_holdout)
        tampered_args = run_args(
            tampered,
            root / "tampered-receipts",
            forged_public_path,
            forged_holdout_path,
            base_path,
        )
        tampered_args.manifest_change_reason = "Adversarial evaluator change fixture."
        tampered_receipt_path = improvement.record_run(tampered_args)
        tampered_receipt = improvement._load_json(tampered_receipt_path)
        tampered_approval_payload = approval_payload(
            base,
            tampered_receipt,
            forged_public,
            forged_holdout,
        )
        tampered_approval_payload["manifest_change_approved"] = True
        _, tampered_approval_path = improvement._seal_json(
            tampered_approval_payload,
            id_field="approval_id",
            id_prefix="approval",
            filename_prefix="approval",
            out_dir=root / "tampered-approval",
        )
        tampered_gate_path, tampered_eligible = improvement.gate(
            argparse.Namespace(
                approval_receipt=tampered_approval_path,
                base_receipt=base_path,
                candidate_receipt=tampered_receipt_path,
                candidate_skill_root=tampered,
                grader_id="independent-grader",
                holdout_result=forged_holdout_path,
                live_skill_root=live,
                out_dir=root / "tampered-gate",
                public_result=forged_public_path,
            )
        )
        tampered_gate = improvement._load_json(tampered_gate_path)
        tampered_checks = {
            item["name"]: item for item in tampered_gate["checks"]
        }
        if tampered_eligible:
            raise AssertionError("changed candidate evaluator passed the local gate")
        if tampered_checks["candidate-evaluator-surface-matches-live"]["passed"]:
            raise AssertionError("changed executable evaluator surface was accepted")
        surface_detail = tampered_checks[
            "candidate-evaluator-surface-matches-live"
        ]["detail"]
        for expected_entry in (
            "scripts/run_eval.py",
            "scripts/sitecustomize.py",
            "evals/governance-cases/json.py",
        ):
            if expected_entry not in surface_detail:
                raise AssertionError(
                    f"surface comparison did not report {expected_entry}"
                )
        if tampered_checks["trusted-candidate-public-rerun"]["passed"]:
            raise AssertionError("changed candidate evaluator was rerun")
        if outside_marker.exists():
            raise AssertionError("changed candidate evaluator executed before rejection")
        checks.append("altered-evaluator-is-rejected-before-execution")

    with tempfile.TemporaryDirectory(prefix="abstraction-police-governance-ledger-") as raw:
        root = Path(raw)
        live = root / "live"
        make_skill(live)
        audit_root = root / "audit"
        audit_root.mkdir()

        balanced = zero_findings_document(audit_root, live, limited=False)
        balanced["summary"]["triage"] = {
            "candidates_by_kind": {"repeated_literal": 2, "token_block_clone": 1},
            "candidates_total": 3,
            "dropped_by_class": {"single-file": 2},
            "investigated": 1,
            "not_reached": 0,
            "promoted": 1,
        }
        validate_document(balanced, repo_root=audit_root, require_existing_paths=True)

        missing = zero_findings_document(audit_root, live, limited=False)
        del missing["summary"]
        expect_findings_error(
            lambda: validate_document(
                missing, repo_root=audit_root, require_existing_paths=True
            ),
            "$.summary: required property is missing",
        )

        unbalanced = zero_findings_document(audit_root, live, limited=False)
        unbalanced["summary"]["triage"]["candidates_total"] = 2
        unbalanced["summary"]["triage"]["candidates_by_kind"] = {"repeated_literal": 1}
        expect_findings_error(
            lambda: validate_document(
                unbalanced, repo_root=audit_root, require_existing_paths=True
            ),
            "expected candidates_total 2",
        )

        unreached = zero_findings_document(audit_root, live, limited=False)
        unreached["summary"]["triage"] = {
            "candidates_by_kind": {"repeated_literal": 2},
            "candidates_total": 2,
            "dropped_by_class": {},
            "investigated": 1,
            "not_reached": 1,
            "promoted": 1,
        }
        expect_findings_error(
            lambda: validate_document(
                unreached, repo_root=audit_root, require_existing_paths=True
            ),
            "phrase 'not reached'",
        )
        unreached["limitations"] = {
            "mode": "specified",
            "items": ["1 candidate not reached: investigation stopped at rank 1."],
        }
        validate_document(unreached, repo_root=audit_root, require_existing_paths=True)
        checks.append("triage-ledger-is-enforced")

        scan_root = root / "scan"
        (scan_root / "nested").mkdir(parents=True)
        (scan_root / "real.txt").write_text("a real file\n", encoding="utf-8")
        (scan_root / "nested" / "inner.txt").write_text("another real file\n", encoding="utf-8")
        (scan_root / "link.txt").symlink_to(scan_root / "real.txt")
        (scan_root / "linked-dir").symlink_to(scan_root / "nested")
        evidence = collect_evidence.collect_evidence([scan_root], 16, 40, 80, [])
        if evidence["scan"]["skipped_symlinks"] != ["link.txt", "linked-dir"]:
            raise AssertionError(
                "scanner did not disclose skipped symlinks: "
                f"{evidence['scan']['skipped_symlinks']!r}"
            )
        if evidence["scan"]["artifact_count"] != 2:
            raise AssertionError("scanner followed a symbolic link")
        checks.append("scanner-discloses-skipped-symlinks")

        identity_bearing_cases = {
            "SKILL.md": True,
            "evals/cases/duplicate_subtree/.worktrees/copy1/dot-git": True,
            "evals/governance-cases/test_governance.py": True,
            "scripts/run_eval.py": True,
            "evals/cases/example/.DS_Store": False,
            "evals/cases/example/.git": False,
            "evals/governance-cases/__pycache__/test_governance.cpython-312.pyc": False,
            "scripts/__pycache__/run_eval.cpython-39.pyc": False,
        }
        for name, expected in sorted(identity_bearing_cases.items()):
            actual = run_eval.identity_bearing(Path(name))
            if actual is not expected:
                raise AssertionError(
                    f"identity_bearing({name!r}) returned {actual}, expected {expected}"
                )
        if not IGNORED_TREE_DIRS >= {".git", "__pycache__"} or ".DS_Store" not in IGNORED_TREE_FILES:
            raise AssertionError("the shared ignore sets no longer cover bytecode and OS cruft")
        checks.append("evaluator-identity-ignores-bytecode-and-os-cruft")

    return sorted(checks)


def main() -> int:
    checks = run_checks()
    result = {
        "checks": checks,
        "schema_version": "1.0",
        "status": "passed",
    }
    sys.stdout.buffer.write(compact_bytes(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
