#!/usr/bin/env python3
"""Govern Abstraction Police improvement proposals and promotion evidence.

The script is intentionally local, deterministic, and standard-library only.
It never edits or promotes a live skill.  It can:

* record content-addressed, non-authorizing audit learning;
* record a content-addressed immutable evaluation receipt;
* create a request and optional patch artifact outside the live skill; and
* emit a pass/fail promotion-gate receipt after public and sealed holdout runs.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from validate_findings import (
    FindingsValidationError,
    canonical_json_bytes,
    validate_document,
)


SKILL_ROOT = Path(__file__).resolve().parent.parent
UNKNOWN = "[unknown]"
NOT_APPLICABLE = "[not-applicable]"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
RECEIPT_ID_RE = re.compile(r"^(?:run|promotion)-sha256:[0-9a-f]{64}$")
MODEL_HASH_FIELDS = {
    "toolset_hash",
    "system_prompt_hash",
    "skill_hash",
    "eval_manifest_hash",
    "input_corpus_hash",
}
EVAL_IDENTITY_FILES = (
    "scripts/collect_evidence.py",
    "scripts/improvement.py",
    "scripts/run_eval.py",
    "scripts/validate_findings.py",
    "evals/model-policy.json",
    "evals/rubric.json",
)
EVAL_IDENTITY_DIRECTORIES = (
    "evals/cases",
    "evals/expected",
    "evals/schemas",
)
OPTIONAL_EVAL_IDENTITY_DIRECTORIES = ("evals/governance-cases",)
EXECUTABLE_EVALUATOR_DIRECTORIES = (
    "scripts",
    "evals/governance-cases",
)
IGNORED_TREE_DIRS = {".git", "__pycache__"}
IGNORED_TREE_FILES = {".DS_Store"}
MOVING_MODEL_ALIASES = {
    "current",
    "default",
    "latest",
    "prod",
    "production",
    "stable",
}
MODEL_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@-]{0,199}$")
SCRUBBED_RUNPY_BOOTSTRAP = (
    "import runpy,sys;"
    "module_dir=sys.argv[1];target=sys.argv[2];"
    "sys.path.insert(0,module_dir);"
    "sys.argv=[target]+sys.argv[3:];"
    "runpy.run_path(target,run_name='__main__')"
)


class GovernanceError(ValueError):
    """Raised when governance preconditions are not met."""


def _load_json(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise GovernanceError(f"{path}: cannot load JSON: {exc}") from exc


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical_hash(value: Any) -> str:
    return _sha256(canonical_json_bytes(value))


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise GovernanceError(f"{path}: cannot hash file: {exc}") from exc
    return digest.hexdigest()


def _json_file_hash(path: Path) -> Tuple[Any, str]:
    value = _load_json(path)
    return value, _canonical_hash(value)


def _resolved_directory(path: Path, label: str) -> Path:
    resolved = path.resolve(strict=False)
    if not resolved.is_dir():
        raise GovernanceError(f"{label} is not a directory: {resolved}")
    return resolved


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(parent.resolve(strict=False))
        return True
    except ValueError:
        return False


def _assert_output_separate(out_dir: Path, protected_roots: Iterable[Path]) -> Path:
    resolved = out_dir.resolve(strict=False)
    for protected in protected_roots:
        protected_resolved = protected.resolve(strict=False)
        if resolved == protected_resolved or _is_within(resolved, protected_resolved):
            raise GovernanceError(
                f"output directory {resolved} must be outside protected skill root "
                f"{protected_resolved}"
            )
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def hash_tree(root: Path) -> str:
    """Hash a physical skill tree by sorted relative path and file digest."""

    return tree_identity(root)["sha256"]


def tree_identity(root: Path) -> Dict[str, Any]:
    """Return the exact physical skill-tree identity and identity-bearing file count."""

    root = _resolved_directory(root, "skill root")
    records: List[Tuple[str, str]] = []
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
        relative = path.relative_to(root)
        if any(part in IGNORED_TREE_DIRS for part in relative.parts):
            continue
        if path.name in IGNORED_TREE_FILES:
            continue
        if path.is_symlink():
            raise GovernanceError(f"skill identity refuses symlink: {path}")
        if path.is_file():
            records.append((relative.as_posix(), _file_hash(path)))
    if not records:
        raise GovernanceError(f"skill tree has no identity-bearing files: {root}")
    digest = hashlib.sha256()
    for relative, file_digest in records:
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(file_digest.encode("ascii"))
        digest.update(b"\n")
    return {"file_count": len(records), "sha256": digest.hexdigest()}


def _immutable_write(path: Path, payload: bytes) -> Path:
    """Create a read-only artifact, or verify an identical existing artifact."""

    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o444)
    except FileExistsError:
        if path.read_bytes() != payload:
            raise GovernanceError(f"{path}: content-addressed artifact collision")
        return path
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    path.chmod(stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
    return path


def _seal_json(
    payload: Mapping[str, Any],
    *,
    id_field: str,
    id_prefix: str,
    filename_prefix: str,
    out_dir: Path,
) -> Tuple[Dict[str, Any], Path]:
    if id_field in payload:
        raise GovernanceError(f"unsealed payload already contains {id_field}")
    digest = _canonical_hash(payload)
    sealed = dict(payload)
    sealed[id_field] = f"{id_prefix}-sha256:{digest}"
    encoded = canonical_json_bytes(sealed)
    path = out_dir / f"{filename_prefix}-{digest}.json"
    return sealed, _immutable_write(path, encoded)


def _verify_sealed(document: Mapping[str, Any], id_field: str, prefix: str) -> None:
    identity = document.get(id_field)
    if not isinstance(identity, str):
        raise GovernanceError(f"receipt is missing {id_field}")
    payload = dict(document)
    del payload[id_field]
    expected = f"{prefix}-sha256:{_canonical_hash(payload)}"
    if identity != expected:
        raise GovernanceError(
            f"receipt {id_field} is not content-addressed: expected {expected}, got {identity}"
        )


def _load_run_receipt(path: Path) -> Dict[str, Any]:
    receipt = _load_json(path)
    if not isinstance(receipt, dict) or receipt.get("kind") != "run-receipt":
        raise GovernanceError(f"{path}: not a run receipt")
    _verify_sealed(receipt, "receipt_id", "run")
    skill_hash = receipt.get("skill_hash")
    if not isinstance(skill_hash, str) or SHA256_RE.fullmatch(skill_hash) is None:
        raise GovernanceError(f"{path}: invalid skill_hash")
    if receipt.get("skill_identity") != f"skill-sha256:{skill_hash}":
        raise GovernanceError(f"{path}: skill identity does not match skill hash")
    return receipt


def _load_model_policy(path: Path) -> Tuple[Dict[str, Any], str]:
    value, digest = _json_file_hash(path)
    if not isinstance(value, dict):
        raise GovernanceError(f"{path}: model policy must be an object")
    fields = value.get("comparison_key_fields")
    if not isinstance(fields, list) or not fields or not all(isinstance(item, str) for item in fields):
        raise GovernanceError(f"{path}: invalid comparison_key_fields")
    return value, digest


def _manifest_identity(manifest: Any, path: Path) -> str:
    """Validate and return run_eval.py's declared public-suite identity."""

    if not isinstance(manifest, dict):
        raise GovernanceError(f"{path}: evaluation manifest must be an object")
    identity = manifest.get("identity_sha256")
    if not isinstance(identity, str) or SHA256_RE.fullmatch(identity) is None:
        raise GovernanceError(f"{path}: invalid identity_sha256")
    if manifest.get("algorithm") != "sha256":
        raise GovernanceError(f"{path}: evaluation manifest algorithm must be sha256")
    if manifest.get("evaluation_scope") != "public-regression":
        raise GovernanceError(f"{path}: evaluation_scope must be public-regression")
    files = manifest.get("files")
    if not isinstance(files, dict) or not files:
        raise GovernanceError(f"{path}: evaluation manifest must bind at least one file")
    skill_root = path.resolve(strict=False).parent.parent
    declared_names: set[str] = set()
    for name, digest in files.items():
        if (
            not isinstance(name, str)
            or not name
            or not isinstance(digest, str)
            or SHA256_RE.fullmatch(digest) is None
        ):
            raise GovernanceError(f"{path}: invalid manifest file hash entry")
        pure_name = PurePosixPath(name)
        if (
            pure_name.is_absolute()
            or ".." in pure_name.parts
            or "." in pure_name.parts
            or "\\" in name
            or pure_name.as_posix() != name
        ):
            raise GovernanceError(f"{path}: unsafe or non-normalized manifest path {name!r}")
        target = skill_root.joinpath(*pure_name.parts)
        try:
            target.resolve(strict=False).relative_to(skill_root)
        except ValueError as exc:
            raise GovernanceError(f"{path}: manifest path escapes skill root: {name!r}") from exc
        if target.is_symlink() or not target.is_file():
            raise GovernanceError(f"{path}: declared manifest file is missing: {name!r}")
        if _file_hash(target) != digest:
            raise GovernanceError(f"{path}: declared file hash mismatch: {name!r}")
        declared_names.add(name)

    actual_paths: List[Path] = []
    for relative in EVAL_IDENTITY_FILES:
        candidate = skill_root / relative
        if not candidate.is_file():
            raise GovernanceError(f"{path}: required evaluator input is missing: {relative!r}")
        actual_paths.append(candidate)
    for relative in EVAL_IDENTITY_DIRECTORIES + OPTIONAL_EVAL_IDENTITY_DIRECTORIES:
        directory = skill_root / relative
        if relative in EVAL_IDENTITY_DIRECTORIES and not directory.is_dir():
            raise GovernanceError(f"{path}: required evaluator directory is missing: {relative!r}")
        if directory.is_dir():
            actual_paths.extend(item for item in directory.rglob("*") if item.is_file())
    actual_names = {item.relative_to(skill_root).as_posix() for item in actual_paths}
    if actual_names != declared_names:
        missing = sorted(declared_names - actual_names)
        extra = sorted(actual_names - declared_names)
        raise GovernanceError(
            f"{path}: manifest inventory mismatch; missing={missing}, unlisted={extra}"
        )
    identity_payload = {key: value for key, value in manifest.items() if key != "identity_sha256"}
    encoded = (
        json.dumps(identity_payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    computed = _sha256(encoded)
    if identity != computed:
        raise GovernanceError(
            f"{path}: identity_sha256 does not match the manifest identity payload"
        )
    return identity


def _manifest_public_case_ids(manifest: Any, path: Path) -> List[str]:
    if not isinstance(manifest, dict):
        raise GovernanceError(f"{path}: evaluation manifest must be an object")
    case_ids = manifest.get("public_case_ids")
    if (
        not isinstance(case_ids, list)
        or not case_ids
        or not all(isinstance(item, str) and item for item in case_ids)
        or len(case_ids) != len(set(case_ids))
        or case_ids != sorted(case_ids)
    ):
        raise GovernanceError(
            f"{path}: public_case_ids must be a non-empty sorted unique string array"
        )
    return list(case_ids)


def _comparison_value_missing(field: str, value: Any) -> bool:
    if value in (None, "", UNKNOWN, NOT_APPLICABLE):
        return True
    if field in MODEL_HASH_FIELDS:
        return not isinstance(value, str) or SHA256_RE.fullmatch(value) is None
    return False


def _is_moving_model_alias(value: str) -> bool:
    normalized = value.strip().casefold()
    if normalized in MOVING_MODEL_ALIASES:
        return True
    return any(
        normalized.endswith(suffix)
        for suffix in (":latest", "/latest", "@latest", "-latest")
    )


def _assisted_model_errors(values: Mapping[str, Any], config: Any) -> List[str]:
    errors: List[str] = []
    for field in ("provider", "model_id", "model_revision", "backend_fingerprint", "reasoning_effort"):
        value = values.get(field)
        if not isinstance(value, str) or MODEL_TOKEN_RE.fullmatch(value) is None:
            errors.append(f"{field} must be a non-empty stable identifier")
            continue
        if _comparison_value_missing(field, value):
            errors.append(f"{field} cannot be unknown or not-applicable")
        elif _is_moving_model_alias(value):
            errors.append(f"{field} cannot be a moving alias")
    revision = values.get("model_revision")
    if isinstance(revision, str) and revision == values.get("model_id"):
        errors.append("model_revision must identify an immutable revision, not repeat model_id")
    temperature = values.get("temperature")
    if (
        not isinstance(temperature, (int, float))
        or isinstance(temperature, bool)
        or not math.isfinite(float(temperature))
    ):
        errors.append("temperature must be a finite number")
    seed = values.get("seed")
    if not isinstance(seed, int) or isinstance(seed, bool):
        errors.append("seed must be an integer")
    for field in MODEL_HASH_FIELDS:
        value = values.get(field)
        if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
            errors.append(f"{field} must be a lowercase sha256 hash")
    if config in (None, "", UNKNOWN, NOT_APPLICABLE):
        errors.append("config cannot be unknown or not-applicable")
    return sorted(set(errors))


def _unknown_model_record() -> Dict[str, Any]:
    return {
        "mode": "model-assisted",
        "provider": UNKNOWN,
        "model_id": UNKNOWN,
        "model_revision": UNKNOWN,
        "backend_fingerprint": UNKNOWN,
        "reasoning_effort": UNKNOWN,
        "temperature": UNKNOWN,
        "seed": UNKNOWN,
        "toolset_hash": UNKNOWN,
        "system_prompt_hash": UNKNOWN,
        "input_corpus_hash": UNKNOWN,
        "config": UNKNOWN,
    }


def _model_record(
    *,
    model_policy: Mapping[str, Any],
    model_policy_hash: str,
    model_record_path: Optional[Path],
    model_independent: bool,
    model_id: Optional[str],
    model_config: Optional[str],
    skill_hash: str,
    eval_manifest_hash: str,
) -> Dict[str, Any]:
    if model_independent and (model_record_path or model_id or model_config):
        raise GovernanceError("--model-independent cannot be combined with model metadata")
    if model_record_path:
        raw = _load_json(model_record_path)
        if not isinstance(raw, dict):
            raise GovernanceError("model record must be a JSON object")
        record = dict(raw)
        record.setdefault("mode", "model-assisted")
        record.setdefault("config", UNKNOWN)
    elif model_independent:
        record = {
            "mode": "model-independent",
            "provider": NOT_APPLICABLE,
            "model_id": NOT_APPLICABLE,
            "model_revision": NOT_APPLICABLE,
            "backend_fingerprint": NOT_APPLICABLE,
            "reasoning_effort": NOT_APPLICABLE,
            "temperature": NOT_APPLICABLE,
            "seed": NOT_APPLICABLE,
            "toolset_hash": NOT_APPLICABLE,
            "system_prompt_hash": NOT_APPLICABLE,
            "input_corpus_hash": NOT_APPLICABLE,
            "config": NOT_APPLICABLE,
        }
    else:
        record = _unknown_model_record()
        if model_id:
            record["model_id"] = model_id
        if model_config:
            try:
                record["config"] = json.loads(model_config)
            except json.JSONDecodeError as exc:
                raise GovernanceError("--model-config must be valid JSON") from exc

    mode = record.get("mode")
    if mode not in {"model-assisted", "model-independent"}:
        raise GovernanceError("model mode must be model-assisted or model-independent")
    comparison_fields = list(model_policy["comparison_key_fields"])
    injected = {
        "skill_hash": skill_hash,
        "eval_manifest_hash": eval_manifest_hash,
    }
    comparison_values: Dict[str, Any] = {}
    missing: List[str] = []
    for field in comparison_fields:
        value = injected.get(field, record.get(field, UNKNOWN))
        comparison_values[field] = value
        if mode == "model-assisted" and _comparison_value_missing(field, value):
            missing.append(field)
    config = record.get("config", UNKNOWN)
    if mode == "model-assisted" and config in (None, "", UNKNOWN):
        missing.append("config")
    if mode == "model-assisted":
        assisted_errors = _assisted_model_errors(comparison_values, config)
        if assisted_errors:
            raise GovernanceError(
                "invalid assisted model record: " + "; ".join(assisted_errors)
            )
    intrinsic_fields = {
        key: value
        for key, value in comparison_values.items()
        if key not in {"skill_hash", "eval_manifest_hash"}
    }
    intrinsic_fields["config_hash"] = _canonical_hash(config)
    authority = "model-independent"
    if mode == "model-assisted":
        authority = "eligible" if not missing else "inconclusive"
    return {
        "mode": mode,
        "config": config,
        "config_hash": _canonical_hash(config),
        "comparison_key_fields": comparison_values,
        "comparison_key": f"model-comparison-sha256:{_canonical_hash(comparison_values)}",
        "intrinsic_key": f"model-intrinsic-sha256:{_canonical_hash(intrinsic_fields)}",
        "missing_comparison_fields": sorted(set(missing)),
        "promotion_authority": authority,
        "model_policy_hash": model_policy_hash,
    }


def _model_integrity_errors(
    model: Any,
    *,
    model_policy: Mapping[str, Any],
    model_policy_hash: str,
    skill_hash: str,
    eval_manifest_hash: str,
) -> List[str]:
    """Recompute every derived model field instead of trusting receipt claims."""

    if not isinstance(model, dict):
        return ["model record is not an object"]
    errors: List[str] = []
    mode = model.get("mode")
    if mode not in {"model-assisted", "model-independent"}:
        return ["unsupported model mode"]
    fields = list(model_policy["comparison_key_fields"])
    values = model.get("comparison_key_fields")
    if not isinstance(values, dict) or set(values) != set(fields):
        return ["comparison key fields do not exactly match target model policy"]
    if model.get("model_policy_hash") != model_policy_hash:
        errors.append("model policy hash does not match target skill")
    if values.get("skill_hash") != skill_hash:
        errors.append("model comparison skill_hash does not match receipt skill")
    if values.get("eval_manifest_hash") != eval_manifest_hash:
        errors.append("model comparison eval_manifest_hash does not match target manifest")

    config = model.get("config", UNKNOWN)
    expected_config_hash = _canonical_hash(config)
    if model.get("config_hash") != expected_config_hash:
        errors.append("config_hash is not derived from canonical config")
    expected_comparison_key = f"model-comparison-sha256:{_canonical_hash(values)}"
    if model.get("comparison_key") != expected_comparison_key:
        errors.append("comparison_key is not derived from comparison_key_fields")
    intrinsic_fields = {
        key: value
        for key, value in values.items()
        if key not in {"skill_hash", "eval_manifest_hash"}
    }
    intrinsic_fields["config_hash"] = expected_config_hash
    expected_intrinsic_key = f"model-intrinsic-sha256:{_canonical_hash(intrinsic_fields)}"
    if model.get("intrinsic_key") != expected_intrinsic_key:
        errors.append("intrinsic_key is not derived from intrinsic model fields")

    if mode == "model-assisted":
        errors.extend(_assisted_model_errors(values, config))

    missing = [
        field for field in fields if mode == "model-assisted" and _comparison_value_missing(field, values[field])
    ]
    if mode == "model-assisted" and config in (None, "", UNKNOWN):
        missing.append("config")
    expected_missing = sorted(set(missing))
    if model.get("missing_comparison_fields") != expected_missing:
        errors.append("missing comparison fields were not recomputed faithfully")
    expected_authority = "model-independent"
    if mode == "model-assisted":
        expected_authority = "eligible" if not expected_missing else "inconclusive"
    if model.get("promotion_authority") != expected_authority:
        errors.append("promotion authority is inconsistent with comparison completeness")
    if mode == "model-independent":
        injected = {"skill_hash", "eval_manifest_hash"}
        if any(values[field] != NOT_APPLICABLE for field in fields if field not in injected):
            errors.append("model-independent fields must be [not-applicable]")
        if config != NOT_APPLICABLE:
            errors.append("model-independent config must be [not-applicable]")
    return errors


def _normalize_status(status: Any) -> str:
    if status not in {"passed", "failed", "error"}:
        raise GovernanceError(f"unsupported evaluation status: {status!r}")
    return str(status)


def summarize_result(
    value: Any,
    suite: str,
    expected_public_identity: Optional[str] = None,
    expected_public_case_ids: Optional[Sequence[str]] = None,
    expected_subject_hash: Optional[str] = None,
    expected_holdout_model_key: Optional[str] = None,
    expected_holdout_input_corpus_hash: Optional[str] = None,
) -> Dict[str, Any]:
    """Normalize the public runner or explicit holdout result into a receipt summary."""

    if suite not in {"public", "holdout"}:
        raise GovernanceError(f"unsupported suite {suite!r}")
    if not isinstance(value, dict) or value.get("schema_version") != "1.0":
        raise GovernanceError(f"{suite} result must be a schema_version 1.0 object")
    if suite == "public":
        if "cases" not in value:
            raise GovernanceError("public evidence must be native run_eval.py case output")
        identity = value.get("identity")
        if not isinstance(identity, dict) or identity.get("status") != "passed":
            raise GovernanceError("public result requires a passed identity object")
        public_identity = identity.get("sha256")
        if not isinstance(public_identity, str) or SHA256_RE.fullmatch(public_identity) is None:
            raise GovernanceError("public result identity.sha256 must be a sha256 hash")
        if expected_public_identity is not None and public_identity != expected_public_identity:
            raise GovernanceError(
                "public result identity.sha256 does not match the target skill manifest"
            )
        subject = value.get("subject")
        if not isinstance(subject, dict) or subject.get("status") != "passed":
            raise GovernanceError("public result requires a passed subject object")
        subject_hash = subject.get("sha256")
        subject_count = subject.get("file_count")
        if not isinstance(subject_hash, str) or SHA256_RE.fullmatch(subject_hash) is None:
            raise GovernanceError("public result subject.sha256 must be a sha256 hash")
        if not isinstance(subject_count, int) or isinstance(subject_count, bool) or subject_count < 1:
            raise GovernanceError("public result subject.file_count must be an integer >= 1")
        if expected_subject_hash is not None and subject_hash != expected_subject_hash:
            raise GovernanceError(
                "public result subject.sha256 does not match the evaluated skill tree"
            )
    else:
        if "cases" in value:
            raise GovernanceError("external holdout evidence must use the explicit result form")
        external_identity = value.get("external_suite_identity")
        if not isinstance(external_identity, str) or SHA256_RE.fullmatch(external_identity) is None:
            raise GovernanceError(
                "holdout result external_suite_identity must be a sha256 hash"
            )
        subject_hash = value.get("subject_sha256")
        if not isinstance(subject_hash, str) or SHA256_RE.fullmatch(subject_hash) is None:
            raise GovernanceError("holdout result subject_sha256 must be a sha256 hash")
        if expected_subject_hash is not None and subject_hash != expected_subject_hash:
            raise GovernanceError(
                "holdout result subject_sha256 does not match the evaluated skill tree"
            )
        holdout_manifest_identity = value.get("eval_manifest_identity")
        if (
            not isinstance(holdout_manifest_identity, str)
            or SHA256_RE.fullmatch(holdout_manifest_identity) is None
        ):
            raise GovernanceError(
                "holdout result eval_manifest_identity must be a sha256 hash"
            )
        if (
            expected_public_identity is not None
            and holdout_manifest_identity != expected_public_identity
        ):
            raise GovernanceError(
                "holdout result eval_manifest_identity does not match the target manifest"
            )
        holdout_model_key = value.get("model_intrinsic_key")
        if holdout_model_key != NOT_APPLICABLE and (
            not isinstance(holdout_model_key, str)
            or re.fullmatch(r"model-intrinsic-sha256:[0-9a-f]{64}", holdout_model_key) is None
        ):
            raise GovernanceError(
                "holdout result model_intrinsic_key must be immutable or [not-applicable]"
            )
        if (
            expected_holdout_model_key is not None
            and holdout_model_key != expected_holdout_model_key
        ):
            raise GovernanceError(
                "holdout result model_intrinsic_key does not match the evaluated model"
            )
        holdout_input_corpus_hash = value.get("input_corpus_hash")
        if (
            not isinstance(holdout_input_corpus_hash, str)
            or SHA256_RE.fullmatch(holdout_input_corpus_hash) is None
        ):
            raise GovernanceError("holdout result input_corpus_hash must be a sha256 hash")
        if (
            expected_holdout_input_corpus_hash is not None
            and holdout_input_corpus_hash != expected_holdout_input_corpus_hash
        ):
            raise GovernanceError(
                "holdout result input_corpus_hash does not match the model comparison corpus"
            )
    status = _normalize_status(value.get("status"))
    if "cases" in value:
        cases = value.get("cases")
        if not isinstance(cases, list) or not cases:
            raise GovernanceError(f"{suite} result cases must be a non-empty array")
        case_ids: List[str] = []
        tests_passed = 0
        tests_failed = 0
        regressions = 0
        deterministic = True
        for index, case in enumerate(cases):
            if not isinstance(case, dict):
                raise GovernanceError(f"{suite} case {index} must be an object")
            name = case.get("name")
            if not isinstance(name, str) or not name:
                raise GovernanceError(f"{suite} case {index} has no name")
            case_ids.append(name)
            case_status = _normalize_status(case.get("status"))
            if case_status == "passed":
                tests_passed += 1
            else:
                tests_failed += 1
            if case.get("expected_match") is not True:
                regressions += 1
            if case.get("byte_identical") is not True:
                deterministic = False
        if len(set(case_ids)) != len(case_ids):
            raise GovernanceError(f"{suite} result contains duplicate case names")
        if expected_public_case_ids is not None and set(case_ids) != set(expected_public_case_ids):
            raise GovernanceError(
                "public result must contain the exact full case set declared by the manifest"
            )
        if status == "passed" and (tests_failed != 0 or regressions != 0):
            raise GovernanceError(
                f"{suite} status passed is inconsistent with failed or regressed cases"
            )
        if status == "failed" and tests_failed == 0 and regressions == 0:
            raise GovernanceError(f"{suite} status failed has no failed or regressed case")
        summary = {
            "suite": suite,
            "status": status,
            "deterministic": deterministic,
            "tests_discovered": len(cases),
            "tests_passed": tests_passed,
            "tests_failed": tests_failed,
            "regressions": regressions,
            "case_ids": sorted(set(case_ids)),
        }
    else:
        if value.get("suite") != suite:
            raise GovernanceError(f"explicit result suite does not match {suite}")
        integer_fields = ("tests_discovered", "tests_passed", "tests_failed", "regressions")
        for field in integer_fields:
            number = value.get(field)
            if not isinstance(number, int) or isinstance(number, bool) or number < 0:
                raise GovernanceError(f"{suite} result {field} must be an integer >= 0")
        if not isinstance(value.get("deterministic"), bool):
            raise GovernanceError(f"{suite} result deterministic must be boolean")
        if value["tests_passed"] + value["tests_failed"] != value["tests_discovered"]:
            raise GovernanceError(
                f"{suite} result arithmetic requires tests_passed + tests_failed "
                "== tests_discovered"
            )
        if status == "passed" and (
            value["tests_failed"] != 0 or value["regressions"] != 0
        ):
            raise GovernanceError(
                f"{suite} status passed is inconsistent with failures or regressions"
            )
        if status == "failed" and value["tests_failed"] == 0 and value["regressions"] == 0:
            raise GovernanceError(f"{suite} status failed has no failed test or regression")
        failures = value.get("failures")
        if not isinstance(failures, list) or not all(isinstance(item, str) for item in failures):
            raise GovernanceError(f"{suite} result failures must be an array of strings")
        if status == "passed" and failures:
            raise GovernanceError(f"{suite} passed result must have an empty failures array")
        if failures and value["tests_failed"] == 0 and value["regressions"] == 0:
            raise GovernanceError(
                f"{suite} failures require a failed test or regression counter"
            )
        case_ids = value.get("case_ids")
        if not isinstance(case_ids, list) or not all(isinstance(item, str) for item in case_ids):
            raise GovernanceError(f"{suite} result case_ids must be strings")
        if len(case_ids) != len(set(case_ids)):
            raise GovernanceError(f"{suite} result case_ids must be unique")
        if len(case_ids) != value["tests_discovered"]:
            raise GovernanceError(
                f"{suite} result case_ids count must equal tests_discovered"
            )
        summary = {
            "suite": suite,
            "status": status,
            "deterministic": value["deterministic"],
            "tests_discovered": value["tests_discovered"],
            "tests_passed": value["tests_passed"],
            "tests_failed": value["tests_failed"],
            "regressions": value["regressions"],
            "case_ids": sorted(set(case_ids)),
        }
    if suite == "holdout":
        for field in ("sealed", "grader_owned", "candidate_access_ended"):
            summary[field] = value.get(field) is True
        grader_id = value.get("grader_id")
        summary["grader_id"] = grader_id if isinstance(grader_id, str) else UNKNOWN
        summary["external_suite_identity"] = external_identity
        summary["eval_manifest_identity"] = holdout_manifest_identity
        summary["input_corpus_hash"] = holdout_input_corpus_hash
        summary["model_intrinsic_key"] = holdout_model_key
        summary["subject_sha256"] = subject_hash
    else:
        summary["public_suite_identity"] = public_identity
        summary["subject_sha256"] = subject_hash
    summary["result_hash"] = _canonical_hash(value)
    return summary


def _parse_result_specs(specs: Sequence[str]) -> List[Tuple[str, Path]]:
    parsed: List[Tuple[str, Path]] = []
    seen: set[str] = set()
    for spec in specs:
        suite, separator, raw_path = spec.partition("=")
        if not separator or suite not in {"public", "holdout"} or not raw_path:
            raise GovernanceError("--result must be public=/path/result.json or holdout=/path/result.json")
        if suite in seen:
            raise GovernanceError(f"duplicate result suite: {suite}")
        seen.add(suite)
        parsed.append((suite, Path(raw_path)))
    return parsed


def _change_record(before: Any, after: Any, reason: Optional[str], label: str) -> Optional[Dict[str, Any]]:
    changed = before != after
    if changed and not reason:
        raise GovernanceError(f"{label} changed without an explicit change reason")
    if not changed and reason:
        raise GovernanceError(f"{label} change reason supplied, but value did not change")
    if not changed:
        return None
    return {"from": before, "to": after, "reason": reason}


def record_run(args: argparse.Namespace) -> Path:
    skill_root = _resolved_directory(args.skill_root, "skill root")
    out_dir = _assert_output_separate(args.out_dir, (skill_root,))
    skill_hash = hash_tree(skill_root)
    expected_manifest = (skill_root / "evals" / "manifest.json").resolve(strict=False)
    supplied_manifest = args.eval_manifest.resolve(strict=False)
    if supplied_manifest != expected_manifest or not expected_manifest.is_file():
        raise GovernanceError(
            "--eval-manifest must be the target skill's own evals/manifest.json"
        )
    manifest, eval_manifest_hash = _json_file_hash(expected_manifest)
    public_suite_identity = _manifest_identity(manifest, expected_manifest)
    public_case_ids = _manifest_public_case_ids(manifest, expected_manifest)
    scanner_path = skill_root / "scripts" / "collect_evidence.py"
    if not scanner_path.is_file():
        raise GovernanceError(f"target skill scanner is missing: {scanner_path}")
    scanner_hash = _file_hash(scanner_path)
    if not args.scanner_version or args.scanner_version == UNKNOWN:
        raise GovernanceError("scanner version must be declared and cannot be [unknown]")
    expected_model_policy = (skill_root / "evals" / "model-policy.json").resolve(strict=False)
    supplied_model_policy = args.model_policy.resolve(strict=False)
    if supplied_model_policy != expected_model_policy or not expected_model_policy.is_file():
        raise GovernanceError(
            "--model-policy must be the target skill's own evals/model-policy.json"
        )
    model_policy, model_policy_hash = _load_model_policy(expected_model_policy)
    model = _model_record(
        model_policy=model_policy,
        model_policy_hash=model_policy_hash,
        model_record_path=args.model_record,
        model_independent=args.model_independent,
        model_id=args.model_id,
        model_config=args.model_config,
        skill_hash=skill_hash,
        eval_manifest_hash=eval_manifest_hash,
    )

    result_specs = _parse_result_specs(args.result)
    if {suite for suite, _path in result_specs} != {"public", "holdout"}:
        raise GovernanceError("record-run requires exactly one public and one holdout result")
    holdout_model_key = (
        NOT_APPLICABLE
        if model.get("mode") == "model-independent"
        else str(model.get("intrinsic_key"))
    )
    expected_corpus_hash = None
    if model.get("mode") == "model-assisted":
        expected_corpus_hash = str(
            model.get("comparison_key_fields", {}).get("input_corpus_hash")
        )

    summaries: List[Dict[str, Any]] = []
    for suite, result_path in result_specs:
        summaries.append(
            summarize_result(
                _load_json(result_path),
                suite,
                expected_public_identity=public_suite_identity,
                expected_public_case_ids=public_case_ids if suite == "public" else None,
                expected_subject_hash=skill_hash,
                expected_holdout_model_key=(
                    holdout_model_key if suite == "holdout" else None
                ),
                expected_holdout_input_corpus_hash=(
                    expected_corpus_hash if suite == "holdout" else None
                ),
            )
        )
    summaries.sort(key=lambda item: item["suite"])

    payload: Dict[str, Any] = {
        "schema_version": "1.0",
        "kind": "run-receipt",
        "skill_identity": f"skill-sha256:{skill_hash}",
        "skill_hash": skill_hash,
        "eval_manifest_hash": eval_manifest_hash,
        "scanner_version": args.scanner_version,
        "scanner_hash": scanner_hash,
        "model": model,
        "producer_id": args.producer_id,
        "results": summaries,
    }
    if not args.producer_id or args.producer_id == UNKNOWN:
        raise GovernanceError("producer identity must be explicit")

    if args.baseline_receipt:
        baseline = _load_run_receipt(args.baseline_receipt)
        changes: Dict[str, Any] = {}
        model_change = _change_record(
            baseline["model"].get("intrinsic_key"),
            model.get("intrinsic_key"),
            args.model_change_reason,
            "model/config",
        )
        scanner_change = _change_record(
            {
                "version": baseline.get("scanner_version"),
                "sha256": baseline.get("scanner_hash"),
            },
            {"version": args.scanner_version, "sha256": scanner_hash},
            args.scanner_change_reason,
            "scanner version/content",
        )
        manifest_change = _change_record(
            baseline.get("eval_manifest_hash"),
            eval_manifest_hash,
            args.manifest_change_reason,
            "evaluation manifest",
        )
        if model_change:
            changes["model"] = model_change
        if scanner_change:
            changes["scanner"] = scanner_change
        if manifest_change:
            changes["eval_manifest"] = manifest_change
        payload["baseline_receipt_id"] = baseline["receipt_id"]
        payload["declared_changes"] = changes
    elif any((args.model_change_reason, args.scanner_change_reason, args.manifest_change_reason)):
        raise GovernanceError("change reasons require --baseline-receipt")

    _, path = _seal_json(
        payload,
        id_field="receipt_id",
        id_prefix="run",
        filename_prefix="run-receipt",
        out_dir=out_dir,
    )
    return path


def _validate_dispositions(value: Any) -> None:
    if not isinstance(value, dict):
        raise GovernanceError("user dispositions must be an object")
    if value.get("schema_version") != "1.0" or value.get("source") != "explicit-user":
        raise GovernanceError("user dispositions must declare schema_version 1.0 and source explicit-user")
    decided_by = value.get("decided_by")
    if not isinstance(decided_by, str) or not decided_by or decided_by == UNKNOWN:
        raise GovernanceError("user dispositions require an explicit decided_by identity")
    decisions = value.get("decisions")
    allowed = {
        "reuse-existing",
        "extract",
        "centralize",
        "generate",
        "parity",
        "link-and-monitor",
        "keep",
        "needs-evidence",
    }
    if not isinstance(decisions, list) or not decisions:
        raise GovernanceError("user dispositions require at least one decision")
    for index, decision in enumerate(decisions):
        if not isinstance(decision, dict):
            raise GovernanceError(f"user disposition {index} must be an object")
        if set(decision) != {"finding_id", "disposition", "rationale"}:
            raise GovernanceError(f"user disposition {index} has missing or unknown fields")
        if not isinstance(decision["finding_id"], str) or not decision["finding_id"]:
            raise GovernanceError(f"user disposition {index} has no finding_id")
        if decision["disposition"] not in allowed:
            raise GovernanceError(f"user disposition {index} has unsupported disposition")
        if not isinstance(decision["rationale"], str) or not decision["rationale"].strip():
            raise GovernanceError(f"user disposition {index} has no rationale")


def _validate_failures(value: Any) -> None:
    if not isinstance(value, dict):
        raise GovernanceError("failure artifact must be an object")
    has_failures = value.get("status") in {"failed", "error"}
    failures = value.get("failures")
    if isinstance(failures, list) and failures:
        has_failures = True
    cases = value.get("cases")
    if isinstance(cases, list) and any(
        isinstance(case, dict) and case.get("status") in {"failed", "error"}
        for case in cases
    ):
        has_failures = True
    if not has_failures:
        raise GovernanceError("failure artifact contains no declared failure")


def _request_model(model_id: Optional[str], model_config: Optional[str]) -> Dict[str, Any]:
    identifier = model_id or UNKNOWN
    config: Any = UNKNOWN
    if model_config:
        try:
            config = json.loads(model_config)
        except json.JSONDecodeError as exc:
            raise GovernanceError("--model-config must be valid JSON") from exc
    return {"id": identifier, "config": config, "config_hash": _canonical_hash(config)}


def _archive_request_input(value: Any, kind: str, out_dir: Path) -> Dict[str, str]:
    digest = _canonical_hash(value)
    artifact_name = f"input-{kind}-{digest}.json"
    _immutable_write(out_dir / artifact_name, canonical_json_bytes(value))
    return {"kind": kind, "sha256": digest, "artifact_name": artifact_name}


def _load_learning_receipt(path: Path) -> Dict[str, Any]:
    value = _load_json(path)
    if not isinstance(value, dict) or value.get("kind") != "audit-learning-receipt":
        raise GovernanceError(f"{path}: not an audit learning receipt")
    _verify_sealed(value, "receipt_id", "learning")
    if value.get("candidate_authority") is not False:
        raise GovernanceError("audit learning receipt cannot authorize a candidate")
    triggers = value.get("improvement_triggers")
    if not isinstance(triggers, list) or not all(
        trigger in {"evaluation-failure", "explicit-user-disposition"}
        for trigger in triggers
    ):
        raise GovernanceError("audit learning receipt has invalid improvement triggers")
    inputs = value.get("inputs")
    if not isinstance(inputs, list) or not inputs:
        raise GovernanceError("audit learning receipt must bind archived inputs")
    for item in inputs:
        if not isinstance(item, dict):
            raise GovernanceError("audit learning receipt input is not an object")
        artifact_name = item.get("artifact_name")
        digest = item.get("sha256")
        if (
            not isinstance(artifact_name, str)
            or not isinstance(digest, str)
            or SHA256_RE.fullmatch(digest) is None
        ):
            raise GovernanceError("audit learning receipt input binding is invalid")
        artifact = path.parent / artifact_name
        if not artifact.is_file() or _canonical_hash(_load_json(artifact)) != digest:
            raise GovernanceError(
                f"audit learning receipt input is missing or changed: {artifact_name}"
            )
    return value


def _findings_evidence_hash(findings: Mapping[str, Any]) -> str:
    evidence = [
        {
            "finding_id": finding.get("id"),
            "evidence": finding.get("evidence", []),
        }
        for finding in findings.get("findings", [])
        if isinstance(finding, dict)
    ]
    return _canonical_hash(evidence)


def _audit_corpus_identity(
    findings: Mapping[str, Any], raw_evidence_hash: str
) -> Dict[str, Any]:
    """Hash only validated cited files plus scope and exclusion boundaries."""

    audit_root = Path(str(findings["audit"]["root"])).resolve(strict=False)
    source_paths: set[Path] = set()
    for finding in findings.get("findings", []):
        if not isinstance(finding, dict):
            continue
        source_groups = [finding.get("locations", [])]
        source_groups.extend(
            observation.get("sources", [])
            for observation in finding.get("observations", [])
            if isinstance(observation, dict)
        )
        source_groups.extend(
            evidence.get("sources", [])
            for evidence in finding.get("evidence", [])
            if isinstance(evidence, dict)
        )
        for sources in source_groups:
            for source in sources:
                if isinstance(source, dict) and isinstance(source.get("path"), str):
                    source_paths.add(Path(source["path"]).resolve(strict=False))

    records: List[Dict[str, str]] = []
    for path in sorted(source_paths, key=lambda item: item.as_posix()):
        relative = path.relative_to(audit_root).as_posix()
        if path.is_file():
            records.append({"path": relative, "sha256": _file_hash(path), "type": "file"})
        elif path.is_dir():
            records.append({"path": relative, "sha256": _sha256(b"directory"), "type": "directory"})
        else:
            raise GovernanceError(f"validated audit source disappeared: {path}")
    payload = {
        "audit_revision": findings["audit"]["revision"],
        "dirty_state": findings["audit"]["dirty_state"],
        "requested_exclusions": findings["execution"]["requested_exclusions"],
        "raw_evidence_hash": raw_evidence_hash,
        "scope": findings["scope"],
        "sources": records,
    }
    return {
        "file_count": len(records),
        "sha256": _canonical_hash(payload),
    }


def record_audit(args: argparse.Namespace) -> Path:
    """Record a completed, incomplete, failed, or zero-finding audit without authority."""

    skill_root = _resolved_directory(args.skill_root, "skill root")
    findings = _load_json(args.findings)
    validated = validate_document(findings, require_existing_paths=True)
    audit = validated["audit"]
    audit_root = _resolved_directory(Path(audit["root"]), "audited root")
    out_dir = _assert_output_separate(args.out_dir, (skill_root,))
    if not args.producer_id or args.producer_id == UNKNOWN:
        raise GovernanceError("audit producer identity must be explicit")

    skill_before = tree_identity(skill_root)
    raw_evidence = _load_json(args.evidence)
    raw_evidence_hash = _canonical_hash(raw_evidence)
    audit_before = _audit_corpus_identity(validated, raw_evidence_hash)
    scanner_path = skill_root / "scripts" / "collect_evidence.py"
    scanner_hash = _file_hash(scanner_path)
    execution = validated["execution"]
    scanner = execution["scanner"]
    if scanner.get("sha256") != scanner_hash:
        raise GovernanceError(
            "findings execution scanner sha256 does not match the audited skill scanner"
        )
    limitations = validated["limitations"]
    if args.outcome in {"incomplete", "failed"} and limitations.get("mode") != "specified":
        raise GovernanceError(
            "incomplete or failed audits require explicit specified limitations"
        )

    inputs = [
        _archive_request_input(validated, "findings", out_dir),
        _archive_request_input(raw_evidence, "raw-evidence", out_dir),
    ]
    triggers: List[str] = []
    if args.failures:
        failures = _load_json(args.failures)
        _validate_failures(failures)
        inputs.append(_archive_request_input(failures, "failures", out_dir))
        triggers.append("evaluation-failure")
    if args.dispositions:
        dispositions = _load_json(args.dispositions)
        _validate_dispositions(dispositions)
        inputs.append(_archive_request_input(dispositions, "user-dispositions", out_dir))
        triggers.append("explicit-user-disposition")

    stderr = scanner["stderr"]
    payload: Dict[str, Any] = {
        "schema_version": "1.0",
        "kind": "audit-learning-receipt",
        "skill_identity": f"skill-sha256:{skill_before['sha256']}",
        "skill_hash": skill_before["sha256"],
        "audit_subject_identity": f"audit-subject-sha256:{audit_before['sha256']}",
        "audit_subject_file_count": audit_before["file_count"],
        "findings_hash": _canonical_hash(validated),
        "raw_evidence_hash": raw_evidence_hash,
        "evidence_hash": _findings_evidence_hash(validated),
        "execution_hash": _canonical_hash(execution),
        "limitations_hash": _canonical_hash(limitations),
        "limitations_mode": limitations["mode"],
        "findings_count": len(validated["findings"]),
        "outcome": args.outcome,
        "scanner": {
            "version": scanner["version"],
            "sha256": scanner_hash,
            "options_hash": _canonical_hash(scanner["options"]),
            "stderr_status": stderr["status"],
            "stderr_sha256": _sha256(stderr["content"].encode("utf-8")),
        },
        "producer_id": args.producer_id,
        "inputs": sorted(inputs, key=lambda item: (item["kind"], item["sha256"])),
        "improvement_triggers": sorted(set(triggers)),
        "candidate_authority": False,
        "live_skill_modified": False,
    }
    _, receipt_path = _seal_json(
        payload,
        id_field="receipt_id",
        id_prefix="learning",
        filename_prefix="audit-learning",
        out_dir=out_dir,
    )
    if tree_identity(skill_root) != skill_before:
        raise GovernanceError("live skill changed while recording audit learning")
    if _audit_corpus_identity(validated, raw_evidence_hash) != audit_before:
        raise GovernanceError("audited corpus changed while recording audit learning")
    return receipt_path


def propose(args: argparse.Namespace) -> Path:
    live_root = _resolved_directory(args.skill_root, "live skill root")
    out_dir = _assert_output_separate(args.out_dir, (live_root,))
    before_hash = hash_tree(live_root)
    inputs: List[Dict[str, str]] = []
    learning_triggers: set[str] = set()

    if args.learning_receipt:
        learning = _load_learning_receipt(args.learning_receipt)
        if learning.get("skill_hash") != before_hash:
            raise GovernanceError(
                "audit learning receipt is bound to a different live skill identity"
            )
        learning_triggers = set(learning.get("improvement_triggers", []))
        if not learning_triggers:
            raise GovernanceError(
                "audit learning receipt has no evaluation failure or explicit user disposition"
            )
        inputs.append(_archive_request_input(learning, "learning-receipt", out_dir))

    if args.findings:
        findings = _load_json(args.findings)
        validate_document(
            findings,
            require_existing_paths=True,
        )
        inputs.append(_archive_request_input(findings, "findings", out_dir))
    if args.failures:
        failures = _load_json(args.failures)
        _validate_failures(failures)
        inputs.append(_archive_request_input(failures, "failures", out_dir))
    if args.dispositions:
        dispositions = _load_json(args.dispositions)
        _validate_dispositions(dispositions)
        inputs.append(_archive_request_input(dispositions, "user-dispositions", out_dir))
    if not (
        any(item["kind"] in {"failures", "user-dispositions"} for item in inputs)
        or learning_triggers
    ):
        raise GovernanceError("proposal requires evaluation failures or explicit user dispositions")
    if not args.producer_id or args.producer_id == UNKNOWN:
        raise GovernanceError("candidate producer identity must be explicit")

    patch_record: Optional[Dict[str, str]] = None
    if args.candidate_patch:
        if not args.candidate_patch.is_file():
            raise GovernanceError(f"candidate patch does not exist: {args.candidate_patch}")
        patch_hash = _file_hash(args.candidate_patch)
        patch_name = f"candidate-patch-{patch_hash}.patch"
        patch_payload = args.candidate_patch.read_bytes()
        _immutable_write(out_dir / patch_name, patch_payload)
        patch_record = {"artifact_name": patch_name, "sha256": patch_hash}

    seed = {
        "base_skill_hash": before_hash,
        "inputs": sorted(inputs, key=lambda item: (item["kind"], item["sha256"])),
        "patch_hash": patch_record["sha256"] if patch_record else None,
        "producer_id": args.producer_id,
    }
    payload: Dict[str, Any] = {
        "schema_version": "1.0",
        "kind": "improvement-request",
        "base_skill_identity": f"skill-sha256:{before_hash}",
        "base_skill_hash": before_hash,
        "producer_id": args.producer_id,
        "model": _request_model(args.model_id, args.model_config),
        "inputs": seed["inputs"],
        "proposed_candidate_identity": f"candidate-request-sha256:{_canonical_hash(seed)}",
        "live_skill_modified": False,
    }
    if patch_record:
        payload["patch"] = patch_record
    _, path = _seal_json(
        payload,
        id_field="request_id",
        id_prefix="request",
        filename_prefix="improvement-request",
        out_dir=out_dir,
    )
    after_hash = hash_tree(live_root)
    if before_hash != after_hash:
        raise GovernanceError("live skill changed while creating candidate request")
    return path


def _result_by_suite(receipt: Mapping[str, Any], suite: str) -> Optional[Mapping[str, Any]]:
    for result in receipt.get("results", []):
        if isinstance(result, dict) and result.get("suite") == suite:
            return result
    return None


def _evaluator_surface_inventory(skill_root: Path) -> Dict[str, Dict[str, str]]:
    """Inventory every directory and file in the executable evaluator surface."""

    skill_root = _resolved_directory(skill_root, "skill root")
    inventory: Dict[str, Dict[str, str]] = {}
    for relative_directory in EXECUTABLE_EVALUATOR_DIRECTORIES:
        directory = skill_root / relative_directory
        if directory.is_symlink() or not directory.is_dir():
            raise GovernanceError(
                f"executable evaluator directory is missing or unsafe: {relative_directory}"
            )
        inventory[relative_directory + "/"] = {"kind": "directory"}
        for path in sorted(directory.rglob("*"), key=lambda item: item.as_posix()):
            relative = path.relative_to(skill_root).as_posix()
            if path.is_symlink():
                raise GovernanceError(f"executable evaluator surface refuses symlink: {relative}")
            if path.is_dir():
                inventory[relative + "/"] = {"kind": "directory"}
            elif path.is_file():
                inventory[relative] = {
                    "kind": "file",
                    "sha256": _file_hash(path),
                }
            else:
                raise GovernanceError(
                    f"executable evaluator surface refuses special entry: {relative}"
                )
    return inventory


def _evaluator_surfaces_match(
    live_root: Path,
    candidate_root: Path,
) -> Tuple[bool, str, Optional[Dict[str, Dict[str, str]]]]:
    """Require candidate executable evaluator code to equal the trusted baseline."""

    try:
        live = _evaluator_surface_inventory(live_root)
        candidate = _evaluator_surface_inventory(candidate_root)
    except GovernanceError as exc:
        return False, str(exc), None
    if live == candidate:
        return (
            True,
            "candidate executable evaluator inventory and content match live",
            live,
        )

    live_names = set(live)
    candidate_names = set(candidate)
    missing = sorted(live_names - candidate_names)
    extra = sorted(candidate_names - live_names)
    changed = sorted(
        name for name in live_names & candidate_names if live[name] != candidate[name]
    )
    return (
        False,
        "candidate executable evaluator differs from live; local gate will not execute it; "
        f"missing={missing}; extra={extra}; changed={changed}; use an externally isolated "
        "and authenticated review to adopt a new evaluator baseline",
        None,
    )


def _scrubbed_python_environment() -> Dict[str, str]:
    """Return the minimal fixed environment used for trusted-identical evaluators."""

    return {
        "LANG": "C",
        "LC_ALL": "C",
        "PATH": os.defpath,
        "PYTHONHASHSEED": "0",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1",
    }


def _set_copy_read_only(root: Path) -> None:
    for path in sorted(root.rglob("*"), key=lambda item: len(item.parts), reverse=True):
        if path.is_file():
            path.chmod(0o444)
        elif path.is_dir():
            path.chmod(0o555)
    root.chmod(0o555)


def _set_copy_removable(root: Path) -> None:
    if not root.exists():
        return
    root.chmod(0o755)
    for path in sorted(root.rglob("*"), key=lambda item: len(item.parts)):
        if path.is_dir():
            path.chmod(0o755)
        elif path.is_file():
            path.chmod(0o644)


def _trusted_public_rerun(
    skill_root: Path,
    *,
    expected_result_hash: str,
    trusted_evaluator_inventory: Mapping[str, Mapping[str, str]],
    expected_bytes: Optional[bytes] = None,
) -> Tuple[bool, str]:
    """Rerun baseline-identical evaluator code with imports and environment scrubbed."""

    try:
        with tempfile.TemporaryDirectory(prefix="abstraction-police-public-rerun-") as raw:
            copied_root = Path(raw) / "skill"
            shutil.copytree(skill_root, copied_root)
            runner = copied_root / "scripts" / "run_eval.py"
            if not runner.is_file():
                return False, "subject has no scripts/run_eval.py"
            command = [
                sys.executable,
                "-I",
                "-S",
                "-B",
                "-c",
                SCRUBBED_RUNPY_BOOTSTRAP,
                str(runner.parent),
                str(runner),
            ]
            _set_copy_read_only(copied_root)
            try:
                copied_inventory = _evaluator_surface_inventory(copied_root)
                if copied_inventory != trusted_evaluator_inventory:
                    return (
                        False,
                        "copied executable evaluator surface changed before rerun; "
                        "no evaluator subprocess was started",
                    )
                runs = [
                    subprocess.run(
                        command,
                        cwd=raw,
                        env=_scrubbed_python_environment(),
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        check=False,
                        timeout=60,
                    )
                    for _index in range(2)
                ]
            finally:
                _set_copy_removable(copied_root)
    except (OSError, shutil.Error, subprocess.TimeoutExpired) as exc:
        return False, f"trusted public rerun failed: {exc}"

    first, second = runs
    if first.returncode != 0 or second.returncode != 0:
        return False, "public evaluator returned nonzero during trusted rerun"
    if first.stderr or second.stderr:
        return False, "public evaluator emitted stderr during trusted rerun"
    if first.stdout != second.stdout:
        return False, "public evaluator stdout changed across trusted reruns"
    if expected_bytes is not None and first.stdout != expected_bytes:
        return False, "supplied public result bytes do not equal trusted rerun stdout"
    try:
        parsed = json.loads(first.stdout)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return False, "trusted public rerun did not emit JSON"
    if not isinstance(parsed, dict) or parsed.get("status") != "passed":
        return False, "trusted public rerun did not report passed"
    if _canonical_hash(parsed) != expected_result_hash:
        return False, "trusted public rerun hash does not match the bound result"
    return True, "two scrubbed-environment reruns reproduced the exact bound public result"


def _approval(path: Path) -> Dict[str, Any]:
    value = _load_json(path)
    if not isinstance(value, dict):
        raise GovernanceError("approval receipt must be an object")
    required = {
        "schema_version",
        "approval_kind",
        "approval_id",
        "approved",
        "candidate_identity",
        "candidate_skill_hash",
        "base_receipt_id",
        "candidate_receipt_id",
        "grader_id",
        "eval_manifest_hash",
        "model_comparison_key",
        "model_policy_hash",
        "public_result_hash",
        "holdout_result_hash",
        "public_suite_identity",
        "external_suite_identity",
        "approver_id",
        "approved_at",
        "approval_statement",
        "model_change_approved",
        "scanner_change_approved",
        "manifest_change_approved",
    }
    if set(value) != required:
        raise GovernanceError("approval receipt has missing or unknown fields")
    if value.get("schema_version") != "1.0" or value.get("approval_kind") != "explicit-human":
        raise GovernanceError("approval must be an explicit-human schema_version 1.0 receipt")
    if value.get("approved") is not True:
        raise GovernanceError("approval receipt is not approved")
    _verify_sealed(value, "approval_id", "approval")
    for key in ("approval_id", "approver_id", "approval_statement", "grader_id"):
        if not isinstance(value.get(key), str) or not value[key].strip() or value[key] == UNKNOWN:
            raise GovernanceError(f"approval receipt requires explicit {key}")
    try:
        stamp = str(value["approved_at"])
        parsed_stamp = dt.datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        if parsed_stamp.tzinfo is None or parsed_stamp.utcoffset() is None:
            raise ValueError
    except ValueError as exc:
        raise GovernanceError("approval approved_at must be an absolute ISO-8601 date-time") from exc
    for key in ("model_change_approved", "scanner_change_approved", "manifest_change_approved"):
        if not isinstance(value.get(key), bool):
            raise GovernanceError(f"approval {key} must be boolean")
    return value


def gate(args: argparse.Namespace) -> Tuple[Path, bool]:
    live_root = _resolved_directory(args.live_skill_root, "live skill root")
    candidate_root = _resolved_directory(args.candidate_skill_root, "candidate skill root")
    if (
        live_root == candidate_root
        or _is_within(candidate_root, live_root)
        or _is_within(live_root, candidate_root)
    ):
        raise GovernanceError(
            "candidate and live skill roots must be separate, non-nested directories"
        )
    out_dir = _assert_output_separate(args.out_dir, (live_root, candidate_root))
    live_before = hash_tree(live_root)
    candidate_actual_hash = hash_tree(candidate_root)
    live_manifest_path = live_root / "evals" / "manifest.json"
    candidate_manifest_path = candidate_root / "evals" / "manifest.json"
    live_manifest, live_manifest_hash = _json_file_hash(live_manifest_path)
    candidate_manifest, candidate_manifest_hash = _json_file_hash(candidate_manifest_path)
    live_public_identity = _manifest_identity(live_manifest, live_manifest_path)
    candidate_public_identity = _manifest_identity(candidate_manifest, candidate_manifest_path)
    live_public_case_ids = _manifest_public_case_ids(live_manifest, live_manifest_path)
    candidate_public_case_ids = _manifest_public_case_ids(
        candidate_manifest, candidate_manifest_path
    )
    live_model_policy, live_model_policy_hash = _load_model_policy(
        live_root / "evals" / "model-policy.json"
    )
    candidate_model_policy, candidate_model_policy_hash = _load_model_policy(
        candidate_root / "evals" / "model-policy.json"
    )
    live_scanner_hash = _file_hash(live_root / "scripts" / "collect_evidence.py")
    candidate_scanner_hash = _file_hash(candidate_root / "scripts" / "collect_evidence.py")
    base = _load_run_receipt(args.base_receipt)
    candidate = _load_run_receipt(args.candidate_receipt)
    approval = _approval(args.approval_receipt)
    public_value = _load_json(args.public_result)
    holdout_value = _load_json(args.holdout_result)
    candidate_model = candidate.get("model", {})
    candidate_holdout_model_key = (
        NOT_APPLICABLE
        if candidate_model.get("mode") == "model-independent"
        else candidate_model.get("intrinsic_key")
    )
    candidate_input_corpus_hash = None
    if candidate_model.get("mode") == "model-assisted":
        candidate_input_corpus_hash = candidate_model.get(
            "comparison_key_fields", {}
        ).get("input_corpus_hash")
    public = summarize_result(
        public_value,
        "public",
        expected_public_identity=candidate_public_identity,
        expected_public_case_ids=candidate_public_case_ids,
        expected_subject_hash=candidate_actual_hash,
    )
    holdout = summarize_result(
        holdout_value,
        "holdout",
        expected_public_identity=candidate_public_identity,
        expected_subject_hash=candidate_actual_hash,
        expected_holdout_model_key=str(candidate_holdout_model_key),
        expected_holdout_input_corpus_hash=(
            str(candidate_input_corpus_hash)
            if candidate_input_corpus_hash is not None
            else None
        ),
    )

    checks: List[Dict[str, Any]] = []

    def check(name: str, passed: bool, detail: str) -> None:
        checks.append({"name": name, "passed": bool(passed), "detail": detail})

    base_public = _result_by_suite(base, "public")
    base_holdout = _result_by_suite(base, "holdout")
    (
        evaluator_surface_ok,
        evaluator_surface_detail,
        trusted_evaluator_inventory,
    ) = _evaluator_surfaces_match(
        live_root,
        candidate_root,
    )
    check(
        "candidate-evaluator-surface-matches-live",
        evaluator_surface_ok,
        evaluator_surface_detail,
    )
    live_rerun_ok = False
    candidate_rerun_ok = False
    if not evaluator_surface_ok:
        live_rerun_detail = "reruns skipped because candidate evaluator surface differs"
        candidate_rerun_detail = (
            "candidate evaluator was not executed because its executable surface differs"
        )
    else:
        live_rerun_detail = "base receipt has no public result"
        if isinstance(base_public, dict) and isinstance(base_public.get("result_hash"), str):
            if trusted_evaluator_inventory is None:
                raise GovernanceError("trusted evaluator inventory disappeared")
            live_rerun_ok, live_rerun_detail = _trusted_public_rerun(
                live_root,
                expected_result_hash=base_public["result_hash"],
                trusted_evaluator_inventory=trusted_evaluator_inventory,
            )
        try:
            supplied_public_bytes = args.public_result.read_bytes()
        except OSError as exc:
            candidate_rerun_detail = f"cannot read supplied public result bytes: {exc}"
        else:
            candidate_rerun_ok, candidate_rerun_detail = _trusted_public_rerun(
                candidate_root,
                expected_result_hash=public["result_hash"],
                trusted_evaluator_inventory=trusted_evaluator_inventory,
                expected_bytes=supplied_public_bytes,
            )

    if not evaluator_surface_ok:
        candidate_rerun_ok = False

    check("trusted-live-public-rerun", live_rerun_ok, live_rerun_detail)
    check("trusted-candidate-public-rerun", candidate_rerun_ok, candidate_rerun_detail)

    check(
        "base-bound-to-live-tree",
        base.get("skill_hash") == live_before,
        "base receipt skill hash must equal the live directory tree hash",
    )
    check(
        "candidate-bound-to-tree",
        candidate.get("skill_hash") == candidate_actual_hash,
        "candidate receipt skill hash must equal the candidate directory tree hash",
    )
    changed = base.get("skill_hash") != candidate.get("skill_hash")
    check("changed-skill", changed, "an improvement candidate must differ from its base skill")
    check(
        "new-skill-identity",
        not changed or base.get("skill_identity") != candidate.get("skill_identity"),
        "every changed skill must receive a new content-addressed identity",
    )
    check(
        "base-manifest-bound",
        base.get("eval_manifest_hash") == live_manifest_hash,
        "base receipt must bind the live skill's own eval manifest",
    )
    check(
        "candidate-manifest-bound",
        candidate.get("eval_manifest_hash") == candidate_manifest_hash,
        "candidate receipt must bind the candidate skill's own eval manifest",
    )
    check(
        "base-scanner-bound",
        base.get("scanner_hash") == live_scanner_hash,
        "base receipt must bind the live skill's scanner bytes",
    )
    check(
        "candidate-scanner-bound",
        candidate.get("scanner_hash") == candidate_scanner_hash,
        "candidate receipt must bind the candidate skill's scanner bytes",
    )
    check(
        "base-model-policy-bound",
        base.get("model", {}).get("model_policy_hash") == live_model_policy_hash,
        "base receipt must bind the live skill's own model policy",
    )
    check(
        "candidate-model-policy-bound",
        candidate.get("model", {}).get("model_policy_hash") == candidate_model_policy_hash,
        "candidate receipt must bind the candidate skill's own model policy",
    )
    check(
        "baseline-link",
        candidate.get("baseline_receipt_id") == base.get("receipt_id"),
        "candidate run receipt must name the exact base receipt",
    )
    producer = candidate.get("producer_id")
    check(
        "independent-grader",
        isinstance(args.grader_id, str) and bool(args.grader_id) and args.grader_id != producer,
        "grader identity must be explicit and distinct from candidate producer",
    )

    for suite, result in (("public", public), ("holdout", holdout)):
        check(f"{suite}-passed", result["status"] == "passed", f"{suite} status must be passed")
        check(
            f"{suite}-deterministic",
            result["deterministic"] is True,
            f"{suite} result must be byte-stable or explicitly deterministic",
        )
        check(
            f"{suite}-tests-discovered",
            result["tests_discovered"] > 0,
            f"{suite} must discover at least one test",
        )
        check(
            f"{suite}-no-failures",
            result["tests_failed"] == 0,
            f"{suite} must have zero failed tests",
        )
        check(
            f"{suite}-no-regressions",
            result["regressions"] == 0,
            f"{suite} must have zero expected-output regressions",
        )
        bound = _result_by_suite(candidate, suite)
        check(
            f"{suite}-bound-to-receipt",
            isinstance(bound, dict) and bound.get("result_hash") == result["result_hash"],
            f"candidate receipt must bind the exact {suite} result hash",
        )
        identity_field = (
            "public_suite_identity" if suite == "public" else "external_suite_identity"
        )
        check(
            f"{suite}-identity-bound-to-receipt",
            isinstance(bound, dict) and bound.get(identity_field) == result.get(identity_field),
            f"candidate receipt must bind the exact {suite} suite identity",
        )
        baseline = _result_by_suite(base, suite)
        no_case_loss = isinstance(baseline, dict) and set(baseline.get("case_ids", [])) <= set(result["case_ids"])
        check(
            f"{suite}-no-case-loss",
            no_case_loss,
            f"candidate {suite} cases must include every base case",
        )
        no_count_regression = isinstance(baseline, dict) and result["tests_discovered"] >= baseline.get("tests_discovered", 0)
        check(
            f"{suite}-no-count-regression",
            no_count_regression,
            f"candidate {suite} test count must not fall below the base receipt",
        )

    check(
        "base-public-identity-bound",
        isinstance(base_public, dict)
        and base_public.get("public_suite_identity") == live_public_identity,
        "base public result identity must equal the live manifest identity_sha256",
    )
    check(
        "base-public-case-set-bound",
        isinstance(base_public, dict)
        and set(base_public.get("case_ids", [])) == set(live_public_case_ids),
        "base public result must contain the exact case set declared by the live manifest",
    )
    check(
        "candidate-public-identity-bound",
        public.get("public_suite_identity") == candidate_public_identity,
        "candidate public result identity must equal the candidate manifest identity_sha256",
    )
    check(
        "base-public-subject-bound",
        isinstance(base_public, dict)
        and base_public.get("subject_sha256") == live_before,
        "base public result must attest the exact live skill tree",
    )
    check(
        "candidate-public-subject-bound",
        public.get("subject_sha256") == candidate_actual_hash,
        "candidate public result must attest the exact candidate skill tree",
    )
    base_model = base.get("model", {})
    expected_base_holdout_model_key = (
        NOT_APPLICABLE
        if base_model.get("mode") == "model-independent"
        else base_model.get("intrinsic_key")
    )
    check(
        "base-holdout-subject-bound",
        isinstance(base_holdout, dict)
        and base_holdout.get("subject_sha256") == live_before,
        "base holdout result must attest the exact live skill tree",
    )
    check(
        "candidate-holdout-subject-bound",
        holdout.get("subject_sha256") == candidate_actual_hash,
        "candidate holdout result must attest the exact candidate skill tree",
    )
    check(
        "base-holdout-manifest-bound",
        isinstance(base_holdout, dict)
        and base_holdout.get("eval_manifest_identity") == live_public_identity,
        "base holdout result must bind the live evaluator identity",
    )
    check(
        "candidate-holdout-manifest-bound",
        holdout.get("eval_manifest_identity") == candidate_public_identity,
        "candidate holdout result must bind the candidate evaluator identity",
    )
    check(
        "base-holdout-model-bound",
        isinstance(base_holdout, dict)
        and base_holdout.get("model_intrinsic_key") == expected_base_holdout_model_key,
        "base holdout result must bind the applicable model identity",
    )
    check(
        "candidate-holdout-model-bound",
        holdout.get("model_intrinsic_key") == candidate_holdout_model_key,
        "candidate holdout result must bind the applicable model identity",
    )
    check(
        "same-external-holdout-identity",
        isinstance(base_holdout, dict)
        and base_holdout.get("external_suite_identity")
        == holdout.get("external_suite_identity"),
        "baseline and candidate must use the same grader-owned external holdout identity",
    )
    check(
        "same-external-input-corpus",
        isinstance(base_holdout, dict)
        and base_holdout.get("input_corpus_hash") == holdout.get("input_corpus_hash"),
        "baseline and candidate holdout results must use the same input corpus identity",
    )

    check(
        "separate-public-holdout",
        public["result_hash"] != holdout["result_hash"],
        "public and holdout must be distinct result artifacts",
    )
    check(
        "disjoint-public-holdout-cases",
        not (set(public["case_ids"]) & set(holdout["case_ids"])),
        "public and sealed holdout case identifiers must be disjoint",
    )
    check(
        "sealed-holdout",
        holdout.get("sealed") is True
        and holdout.get("grader_owned") is True
        and holdout.get("candidate_access_ended") is True,
        "holdout must be sealed, grader-owned, and run after candidate access ends",
    )
    check(
        "holdout-grader-identity",
        holdout.get("grader_id") == args.grader_id,
        "holdout grader identity must match the independent promotion grader",
    )

    model = candidate.get("model", {})
    base_model_errors = _model_integrity_errors(
        base_model,
        model_policy=live_model_policy,
        model_policy_hash=live_model_policy_hash,
        skill_hash=str(base.get("skill_hash")),
        eval_manifest_hash=str(base.get("eval_manifest_hash")),
    )
    candidate_model_errors = _model_integrity_errors(
        model,
        model_policy=candidate_model_policy,
        model_policy_hash=candidate_model_policy_hash,
        skill_hash=str(candidate.get("skill_hash")),
        eval_manifest_hash=str(candidate.get("eval_manifest_hash")),
    )
    check(
        "base-model-record-integrity",
        not base_model_errors,
        "; ".join(base_model_errors) or "base model record fields recompute exactly",
    )
    check(
        "candidate-model-record-integrity",
        not candidate_model_errors,
        "; ".join(candidate_model_errors) or "candidate model record fields recompute exactly",
    )
    check(
        "model-comparison-complete",
        not candidate_model_errors
        and (
            model.get("mode") == "model-independent"
        or (
            model.get("promotion_authority") == "eligible"
            and model.get("missing_comparison_fields") == []
            )
        ),
        "model-assisted promotion requires immutable revision, backend fingerprint, "
        "configuration, tool, prompt, corpus, skill, and manifest comparison fields",
    )
    changes = candidate.get("declared_changes", {})
    if not isinstance(changes, dict):
        changes = {}
    model_changed = base.get("model", {}).get("intrinsic_key") != model.get("intrinsic_key")
    scanner_changed = {
        "version": base.get("scanner_version"),
        "sha256": base.get("scanner_hash"),
    } != {
        "version": candidate.get("scanner_version"),
        "sha256": candidate.get("scanner_hash"),
    }
    manifest_changed = base.get("eval_manifest_hash") != candidate.get("eval_manifest_hash")
    check(
        "declared-model-change",
        not model_changed or isinstance(changes.get("model"), dict),
        "model/config changes require a declared new baseline reason",
    )
    check(
        "declared-scanner-change",
        not scanner_changed or isinstance(changes.get("scanner"), dict),
        "scanner changes require a declared reason",
    )
    check(
        "declared-manifest-change",
        not manifest_changed or isinstance(changes.get("eval_manifest"), dict),
        "evaluation manifest changes require a declared reason",
    )
    check(
        "approved-model-change",
        not model_changed or approval.get("model_change_approved") is True,
        "explicit approval must authorize a model/config baseline change",
    )
    check(
        "approved-scanner-change",
        not scanner_changed or approval.get("scanner_change_approved") is True,
        "explicit approval must authorize a scanner change",
    )
    check(
        "approved-manifest-change",
        not manifest_changed or approval.get("manifest_change_approved") is True,
        "explicit approval must authorize an evaluation manifest change",
    )

    approval_bindings = {
        "base_receipt_id": base.get("receipt_id"),
        "candidate_receipt_id": candidate.get("receipt_id"),
        "grader_id": args.grader_id,
        "candidate_identity": candidate.get("skill_identity"),
        "candidate_skill_hash": candidate.get("skill_hash"),
        "eval_manifest_hash": candidate.get("eval_manifest_hash"),
        "model_comparison_key": model.get("comparison_key"),
        "model_policy_hash": model.get("model_policy_hash"),
        "public_result_hash": public["result_hash"],
        "holdout_result_hash": holdout["result_hash"],
        "public_suite_identity": public["public_suite_identity"],
        "external_suite_identity": holdout["external_suite_identity"],
    }
    for key, expected in approval_bindings.items():
        check(
            f"approval-binds-{key}",
            approval.get(key) == expected,
            f"approval {key} must bind the exact candidate evidence",
        )

    live_after = hash_tree(live_root)
    check(
        "live-skill-unchanged",
        live_before == live_after,
        "promotion gate is read-only and must not mutate the live skill",
    )
    eligible = all(item["passed"] for item in checks)
    payload = {
        "schema_version": "1.0",
        "kind": "promotion-gate-receipt",
        "base_receipt_id": base["receipt_id"],
        "candidate_receipt_id": candidate["receipt_id"],
        "candidate_identity": candidate["skill_identity"],
        "candidate_subject_sha256": candidate_actual_hash,
        "grader_id": args.grader_id,
        "approval_id": approval["approval_id"],
        "public_result_hash": public["result_hash"],
        "holdout_result_hash": holdout["result_hash"],
        "public_suite_identity": public["public_suite_identity"],
        "external_suite_identity": holdout["external_suite_identity"],
        "checks": checks,
        "eligible": eligible,
    }
    _, path = _seal_json(
        payload,
        id_field="receipt_id",
        id_prefix="promotion",
        filename_prefix="promotion-gate",
        out_dir=out_dir,
    )
    return path, eligible


def _add_model_args(parser: argparse.ArgumentParser) -> None:
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--model-record", type=Path, help="full model comparison record JSON")
    group.add_argument("--model-independent", action="store_true")
    parser.add_argument("--model-id", help="partial model ID; remains inconclusive without full record")
    parser.add_argument("--model-config", help="canonical JSON model config, or '[unknown]' when omitted")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Govern skill improvement without mutating the live skill.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run = subparsers.add_parser("record-run", help="write an immutable run receipt")
    run.add_argument("--skill-root", type=Path, required=True)
    run.add_argument("--eval-manifest", type=Path, required=True)
    run.add_argument("--scanner-version", required=True)
    run.add_argument(
        "--result",
        action="append",
        required=True,
        help="public=/absolute/result.json or holdout=/absolute/result.json; repeat by suite",
    )
    run.add_argument("--producer-id", required=True)
    run.add_argument("--baseline-receipt", type=Path)
    run.add_argument("--model-change-reason")
    run.add_argument("--scanner-change-reason")
    run.add_argument("--manifest-change-reason")
    run.add_argument(
        "--model-policy",
        type=Path,
        required=True,
        help="target skill's own evals/model-policy.json",
    )
    run.add_argument("--out-dir", type=Path, required=True)
    _add_model_args(run)

    audit = subparsers.add_parser(
        "record-audit",
        help="write an immutable non-authorizing audit learning receipt",
    )
    audit.add_argument("--skill-root", type=Path, required=True)
    audit.add_argument("--findings", type=Path, required=True)
    audit.add_argument("--evidence", type=Path, required=True)
    audit.add_argument(
        "--outcome",
        choices=("completed", "incomplete", "failed"),
        required=True,
    )
    audit.add_argument("--failures", type=Path)
    audit.add_argument("--dispositions", type=Path)
    audit.add_argument("--producer-id", required=True)
    audit.add_argument("--out-dir", type=Path, required=True)

    request = subparsers.add_parser("propose", help="create a candidate request/patch artifact")
    request.add_argument("--skill-root", type=Path, required=True)
    request.add_argument("--findings", type=Path)
    request.add_argument("--failures", type=Path)
    request.add_argument("--dispositions", type=Path)
    request.add_argument("--learning-receipt", type=Path)
    request.add_argument("--candidate-patch", type=Path)
    request.add_argument("--producer-id", required=True)
    request.add_argument("--model-id")
    request.add_argument("--model-config")
    request.add_argument("--out-dir", type=Path, required=True)

    promotion = subparsers.add_parser("gate", help="evaluate promotion evidence without promoting")
    promotion.add_argument("--live-skill-root", type=Path, required=True)
    promotion.add_argument("--candidate-skill-root", type=Path, required=True)
    promotion.add_argument("--base-receipt", type=Path, required=True)
    promotion.add_argument("--candidate-receipt", type=Path, required=True)
    promotion.add_argument("--public-result", type=Path, required=True)
    promotion.add_argument("--holdout-result", type=Path, required=True)
    promotion.add_argument("--approval-receipt", type=Path, required=True)
    promotion.add_argument("--grader-id", required=True)
    promotion.add_argument("--out-dir", type=Path, required=True)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "record-run":
            path = record_run(args)
            print(path)
            return 0
        if args.command == "record-audit":
            path = record_audit(args)
            print(path)
            return 0
        if args.command == "propose":
            path = propose(args)
            print(path)
            return 0
        if args.command == "gate":
            path, eligible = gate(args)
            print(path)
            return 0 if eligible else 1
        raise GovernanceError(f"unknown command {args.command}")
    except (GovernanceError, FindingsValidationError) as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
