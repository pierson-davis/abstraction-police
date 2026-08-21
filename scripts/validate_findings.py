#!/usr/bin/env python3
"""Validate and canonically serialize Abstraction Police findings.

This module deliberately uses only the Python standard library.  It validates
the skill's narrow findings schema plus semantic rules JSON Schema cannot
express, especially that similarity evidence cannot prove behavioral
equivalence.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Sequence, Tuple


DEFAULT_SCHEMA = (
    Path(__file__).resolve().parent.parent
    / "evals"
    / "schemas"
    / "findings.schema.json"
)

BEHAVIOR_WORDING = re.compile(
    r"\b(?:behaviorally equivalent|same behavior|identical behavior|"
    r"semantically identical|semantically equivalent|interchangeable)\b",
    re.IGNORECASE,
)
# BEHAVIOR_WORDING is deliberately NOT extended to nominal forms
# ("behavioral equivalence", "functional equivalence", "interchangeability"):
# a tested extension false-positived on a real, correctly bounded disclaimer
# claim ending "...behavioral equivalence between the three was not tested
# and is not claimed."  Disclaimers of a stronger claim are in-bounds prose.
# Any future broadening must carry a clause-scoped negation guard
# regression-tested against that exact claim string.
#
# EXACT_IDENTITY_WORDING carries the lexical-identity rung: wording that
# asserts byte identity requires exact-hash evidence.  It gates on the cited
# evidence TYPES, not on claim_level, because a lower-rung lexical fact
# ("byte-identical", backed by exact-content-hash) may legitimately appear
# inside a higher-level finding; claim_level gating only works for the top
# rung that BEHAVIOR_WORDING polices.  Measured on the real corpus: one true
# positive, zero false positives.  If a false positive is ever observed,
# remove the offending phrase from the list rather than softening the rule.
EXACT_IDENTITY_WORDING = re.compile(
    r"(?<![\w-])(?:byte[- ]identical|bit[- ]identical|byte[- ]for[- ]byte|"
    r"character[- ]for[- ]character|textually identical|identical bytes|"
    r"the same bytes|verbatim|exact (?:copy|copies|duplicate|duplicates))"
    r"(?![\w-])",
    re.IGNORECASE,
)
EXACT_IDENTITY_EVIDENCE = frozenset({"exact-content-hash", "asset-exact-hash"})
ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class FindingsValidationError(ValueError):
    """Raised when one or more findings fail validation."""

    def __init__(self, errors: Sequence[str]):
        self.errors = tuple(errors)
        super().__init__("\n".join(self.errors))


def canonical_json_bytes(value: Any) -> bytes:
    """Return deterministic UTF-8 JSON with a single trailing newline."""

    return (
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def load_json(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise FindingsValidationError((f"{path}: cannot load JSON: {exc}",)) from exc


def _enum(schema: Mapping[str, Any], definition: str, *path: str) -> frozenset[str]:
    """Read a schema-declared enum, failing closed when it is absent.

    ``path`` names one or more nested property names under the definition,
    so ``_enum(schema, "scanner_execution", "stderr", "status")`` reads
    ``$defs.scanner_execution.properties.stderr.properties.status.enum``.
    """

    node: Any = schema.get("$defs") if isinstance(schema, Mapping) else None
    node = node.get(definition) if isinstance(node, Mapping) else None
    for name in path:
        properties = node.get("properties") if isinstance(node, Mapping) else None
        node = properties.get(name) if isinstance(properties, Mapping) else None
    values = node.get("enum") if isinstance(node, Mapping) else None
    if not _is_string_list(values) or not values:
        location = ".".join(("$defs", definition) + tuple(path))
        raise FindingsValidationError(
            (f"schema: {location}.enum: expected a non-empty enum of strings",)
        )
    return frozenset(values)


def _is_string_list(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def _check_keys(
    value: Mapping[str, Any],
    *,
    required: Iterable[str],
    allowed: Iterable[str],
    prefix: str,
    errors: list[str],
) -> None:
    required_set = set(required)
    allowed_set = set(allowed)
    for missing in sorted(required_set - set(value)):
        errors.append(f"{prefix}.{missing}: required property is missing")
    for extra in sorted(set(value) - allowed_set):
        errors.append(f"{prefix}.{extra}: unknown property")


def _validate_source(
    source: Any,
    *,
    prefix: str,
    errors: list[str],
    repo_root: Optional[Path],
    require_existing_paths: bool,
    locator_kinds: frozenset[str],
) -> Optional[Tuple[str, Optional[int], Optional[int], Optional[str], Optional[str]]]:
    if not isinstance(source, dict):
        errors.append(f"{prefix}: expected an object")
        return None
    _check_keys(
        source,
        required=("path",),
        allowed=(
            "path",
            "start_line",
            "end_line",
            "sha256",
            "locator_kind",
            "locator",
        ),
        prefix=prefix,
        errors=errors,
    )
    raw_path = source.get("path")
    if not isinstance(raw_path, str) or not raw_path:
        errors.append(f"{prefix}.path: expected a non-empty string")
        return None
    if "\x00" in raw_path or not os.path.isabs(raw_path):
        errors.append(f"{prefix}.path: must be an absolute filesystem path")
    normalized = os.path.normpath(raw_path)
    if normalized != raw_path:
        errors.append(f"{prefix}.path: must be normalized without '.' or '..' segments")
    path = Path(raw_path)
    if repo_root is not None:
        try:
            path.resolve(strict=False).relative_to(repo_root.resolve(strict=False))
        except ValueError:
            errors.append(f"{prefix}.path: is outside declared repository root {repo_root}")
    path_exists = path.exists()
    if require_existing_paths and not path_exists:
        errors.append(f"{prefix}.path: does not exist")

    start = source.get("start_line")
    end = source.get("end_line")
    if start is not None and (not isinstance(start, int) or isinstance(start, bool) or start < 1):
        errors.append(f"{prefix}.start_line: expected an integer >= 1")
    if end is not None and (not isinstance(end, int) or isinstance(end, bool) or end < 1):
        errors.append(f"{prefix}.end_line: expected an integer >= 1")
    if end is not None and start is None:
        errors.append(f"{prefix}.end_line: requires start_line")
    if isinstance(start, int) and isinstance(end, int) and end < start:
        errors.append(f"{prefix}.end_line: must be >= start_line")
    digest = source.get("sha256")
    if digest is not None and (
        not isinstance(digest, str) or SHA256_PATTERN.fullmatch(digest) is None
    ):
        errors.append(f"{prefix}.sha256: expected 64 lowercase hexadecimal characters")
    elif digest is not None and path_exists:
        if not path.is_file():
            errors.append(f"{prefix}.sha256: can only verify a regular file")
        else:
            try:
                actual_digest = hashlib.sha256(path.read_bytes()).hexdigest()
            except OSError as exc:
                errors.append(f"{prefix}.sha256: cannot read source file: {exc}")
            else:
                if digest != actual_digest:
                    errors.append(f"{prefix}.sha256: does not match source file bytes")
    if path_exists and (start is not None or end is not None):
        if not path.is_file():
            errors.append(f"{prefix}.start_line: line bounds require a regular file")
        else:
            try:
                with path.open("rb") as handle:
                    line_count = sum(1 for _ in handle)
            except OSError as exc:
                errors.append(f"{prefix}.start_line: cannot read source file: {exc}")
            else:
                if isinstance(start, int) and start > line_count:
                    errors.append(
                        f"{prefix}.start_line: {start} exceeds file length {line_count}"
                    )
                if isinstance(end, int) and end > line_count:
                    errors.append(f"{prefix}.end_line: {end} exceeds file length {line_count}")
    locator_kind = source.get("locator_kind")
    locator = source.get("locator")
    if (locator_kind is None) != (locator is None):
        errors.append(f"{prefix}: locator_kind and locator must be supplied together")
    if locator_kind is not None:
        if locator_kind not in locator_kinds:
            errors.append(f"{prefix}.locator_kind: unsupported value {locator_kind!r}")
        if not isinstance(locator, str) or not locator.strip():
            errors.append(f"{prefix}.locator: expected a non-empty string")
    return (
        raw_path,
        start if isinstance(start, int) else None,
        end if isinstance(end, int) else None,
        locator_kind if isinstance(locator_kind, str) else None,
        locator if isinstance(locator, str) else None,
    )


def _validate_metric(metric: Any, *, prefix: str, errors: list[str]) -> None:
    if not isinstance(metric, dict):
        errors.append(f"{prefix}: expected an object")
        return
    _check_keys(
        metric,
        required=("name", "value"),
        allowed=("name", "value", "unit"),
        prefix=prefix,
        errors=errors,
    )
    if not isinstance(metric.get("name"), str) or not metric.get("name"):
        errors.append(f"{prefix}.name: expected a non-empty string")
    value = metric.get("value")
    if not isinstance(value, (str, int, float, bool)):
        errors.append(f"{prefix}.value: expected a string, number, or boolean")
    if isinstance(value, float) and (value != value or value in (float("inf"), float("-inf"))):
        errors.append(f"{prefix}.value: NaN and infinity are forbidden")
    if "unit" in metric and not isinstance(metric["unit"], str):
        errors.append(f"{prefix}.unit: expected a string")


def _validate_explicit_list(
    value: Any, *, prefix: str, errors: list[str], modes: frozenset[str]
) -> None:
    if not isinstance(value, dict):
        errors.append(f"{prefix}: expected an explicit-list object")
        return
    _check_keys(
        value,
        required=("mode", "items"),
        allowed=("mode", "items"),
        prefix=prefix,
        errors=errors,
    )
    mode = value.get("mode")
    items = value.get("items")
    if mode not in modes:
        errors.append(f"{prefix}.mode: expected none or specified")
    if not _is_string_list(items) or any(not item.strip() for item in items or []):
        errors.append(f"{prefix}.items: expected unique non-empty strings")
        return
    if len(items) != len(set(items)):
        errors.append(f"{prefix}.items: duplicate values are forbidden")
    if mode == "none" and items:
        errors.append(f"{prefix}.items: mode none requires an empty array")
    if mode == "specified" and not items:
        errors.append(f"{prefix}.items: mode specified requires at least one item")


def _validate_execution(
    value: Any,
    *,
    prefix: str,
    errors: list[str],
    modes: frozenset[str],
    stderr_statuses: frozenset[str],
) -> None:
    if not isinstance(value, dict):
        errors.append(f"{prefix}: expected an object")
        return
    _check_keys(
        value,
        required=("output_directory", "requested_exclusions", "scanner", "commands"),
        allowed=(
            "output_directory",
            "requested_exclusions",
            "scanner",
            "commands",
            "scan_roots",
        ),
        prefix=prefix,
        errors=errors,
    )
    output_directory = value.get("output_directory")
    if not isinstance(output_directory, str) or not os.path.isabs(output_directory):
        errors.append(f"{prefix}.output_directory: must be an absolute filesystem path")
    elif os.path.normpath(output_directory) != output_directory:
        errors.append(f"{prefix}.output_directory: must be normalized")
    _validate_explicit_list(
        value.get("requested_exclusions"),
        prefix=f"{prefix}.requested_exclusions",
        errors=errors,
        modes=modes,
    )
    commands = value.get("commands")
    if not _is_string_list(commands) or not commands or any(not item.strip() for item in commands):
        errors.append(f"{prefix}.commands: expected a non-empty array of commands")
    scan_roots = value.get("scan_roots")
    if scan_roots is not None:
        if not _is_string_list(scan_roots) or not scan_roots:
            errors.append(
                f"{prefix}.scan_roots: expected a non-empty array of absolute paths"
            )
        else:
            for root_index, scan_root in enumerate(scan_roots):
                if not os.path.isabs(scan_root):
                    errors.append(
                        f"{prefix}.scan_roots[{root_index}]: must be an absolute "
                        "filesystem path"
                    )
                elif os.path.normpath(scan_root) != scan_root:
                    errors.append(
                        f"{prefix}.scan_roots[{root_index}]: must be normalized"
                    )

    scanner = value.get("scanner")
    if not isinstance(scanner, dict):
        errors.append(f"{prefix}.scanner: expected an object")
        return
    _check_keys(
        scanner,
        required=("version", "sha256", "options", "stderr"),
        allowed=("version", "sha256", "options", "stderr"),
        prefix=f"{prefix}.scanner",
        errors=errors,
    )
    if not isinstance(scanner.get("version"), str) or not scanner.get("version", "").strip():
        errors.append(f"{prefix}.scanner.version: expected a non-empty string")
    digest = scanner.get("sha256")
    if not isinstance(digest, str) or SHA256_PATTERN.fullmatch(digest) is None:
        errors.append(f"{prefix}.scanner.sha256: expected a lowercase sha256 hash")
    if not _is_string_list(scanner.get("options")):
        errors.append(f"{prefix}.scanner.options: expected an array of strings")
    stderr = scanner.get("stderr")
    if not isinstance(stderr, dict):
        errors.append(f"{prefix}.scanner.stderr: expected an object")
        return
    _check_keys(
        stderr,
        required=("status", "content"),
        allowed=("status", "content"),
        prefix=f"{prefix}.scanner.stderr",
        errors=errors,
    )
    status = stderr.get("status")
    content = stderr.get("content")
    if status not in stderr_statuses:
        errors.append(f"{prefix}.scanner.stderr.status: expected empty or captured")
    if not isinstance(content, str):
        errors.append(f"{prefix}.scanner.stderr.content: expected a string")
    elif status == "empty" and content:
        errors.append(f"{prefix}.scanner.stderr.content: empty status requires empty content")
    elif status == "captured" and not content:
        errors.append(f"{prefix}.scanner.stderr.content: captured status requires content")


def _validate_evidence_provenance(
    value: Any, *, prefix: str, errors: list[str], kinds: frozenset[str]
) -> None:
    if not isinstance(value, dict):
        errors.append(f"{prefix}: expected an object")
        return
    _check_keys(
        value,
        required=("kind", "producer", "method"),
        allowed=("kind", "producer", "method"),
        prefix=prefix,
        errors=errors,
    )
    if value.get("kind") not in kinds:
        errors.append(f"{prefix}.kind: unsupported provenance kind")
    for key in ("producer", "method"):
        if not isinstance(value.get(key), str) or not value.get(key, "").strip():
            errors.append(f"{prefix}.{key}: expected a non-empty string")


def _validate_authority_rule(
    value: Any,
    *,
    prefix: str,
    errors: list[str],
    kinds: frozenset[str],
    bases: frozenset[str],
) -> Optional[str]:
    if not isinstance(value, dict):
        errors.append(f"{prefix}: expected an object")
        return None
    _check_keys(
        value,
        required=("kind", "authority_basis", "rule"),
        allowed=("kind", "authority_basis", "rule"),
        prefix=prefix,
        errors=errors,
    )
    kind = value.get("kind")
    if kind not in kinds:
        errors.append(f"{prefix}.kind: unsupported authority rule kind")
        kind = None
    authority_basis = value.get("authority_basis")
    if authority_basis not in bases:
        errors.append(f"{prefix}.authority_basis: ownership alone is not authority")
    allowed_basis = {
        "authoritative-derivation": {
            "declared-source-of-truth",
            "normative-specification",
            "executable-generation-rule",
        },
        "explicit-parity-invariant": {
            "normative-specification",
            "contractual-invariant",
        },
        "shared-requirement": {
            "declared-source-of-truth",
            "normative-specification",
            "contractual-invariant",
        },
    }
    if kind in allowed_basis and authority_basis not in allowed_basis[kind]:
        errors.append(
            f"{prefix}.authority_basis: is not valid for authority rule kind {kind!r}"
        )
    if not isinstance(value.get("rule"), str) or not value.get("rule", "").strip():
        errors.append(f"{prefix}.rule: expected a non-empty authoritative rule")
    return kind if isinstance(kind, str) else None


def _path_covers(ancestor: str, descendant: str) -> bool:
    """Return True when descendant equals ancestor or sits inside it."""

    normalized = ancestor.rstrip("/") or "/"
    if normalized == "/":
        return descendant.startswith("/")
    return descendant == normalized or descendant.startswith(normalized + "/")


def normalize_document(value: Any) -> dict[str, Any]:
    """Normalize the legacy bare-list form to the versioned document form."""

    if isinstance(value, list):
        return {"schema_version": "1.0", "findings": value}
    if not isinstance(value, dict):
        raise FindingsValidationError(("$: expected an object or a findings array",))
    return value


def validate_document(
    value: Any,
    *,
    schema: Optional[Mapping[str, Any]] = None,
    repo_root: Optional[Path] = None,
    require_existing_paths: bool = False,
) -> dict[str, Any]:
    """Validate findings and return their normalized document form."""

    if schema is None:
        loaded = load_json(DEFAULT_SCHEMA)
        if not isinstance(loaded, dict):
            raise FindingsValidationError((f"{DEFAULT_SCHEMA}: schema must be an object",))
        schema = loaded

    document = normalize_document(value)
    errors: list[str] = []

    # Every controlled vocabulary is single-sourced from the schema; _enum
    # fails closed with a clear error when an expected enum is missing.
    artifact_classes = _enum(schema, "finding", "artifact_class")
    claim_levels = _enum(schema, "finding", "claim_level")
    confidences = _enum(schema, "finding", "confidence")
    severities = _enum(schema, "finding", "severity")
    dispositions = _enum(schema, "finding", "disposition")
    actions = _enum(schema, "finding", "action")
    evidence_types = _enum(schema, "evidence", "type")
    locator_kinds = _enum(schema, "source", "locator_kind")
    provenance_kinds = _enum(schema, "evidence_provenance", "kind")
    authority_kind_values = _enum(schema, "authority_rule", "kind")
    authority_basis_values = _enum(schema, "authority_rule", "authority_basis")
    squint_status_values = _enum(schema, "squint_gate", "status")
    risk_levels = _enum(schema, "risk", "level")
    explicit_list_modes = _enum(schema, "explicit_list", "mode")
    stderr_statuses = _enum(schema, "scanner_execution", "stderr", "status")
    dirty_states = _enum(schema, "audit", "dirty_state")

    top_properties = schema.get("properties", {})
    _check_keys(
        document,
        required=schema.get("required", ()),
        allowed=top_properties,
        prefix="$",
        errors=errors,
    )
    if document.get("schema_version") != "1.0":
        errors.append("$.schema_version: expected '1.0'")

    audit = document.get("audit")
    if not isinstance(audit, dict):
        errors.append("$.audit: expected an object")
    else:
        _check_keys(
            audit,
            required=("root", "revision", "dirty_state", "date", "commands"),
            allowed=("root", "revision", "dirty_state", "date", "commands"),
            prefix="$.audit",
            errors=errors,
        )
        declared_root = audit.get("root")
        if not isinstance(declared_root, str) or not os.path.isabs(declared_root):
            errors.append("$.audit.root: must be an absolute filesystem path")
        elif repo_root is not None and Path(declared_root).resolve(strict=False) != repo_root.resolve(strict=False):
            errors.append("$.audit.root: does not match --repo-root")
        elif repo_root is None:
            repo_root = Path(declared_root)
        if not isinstance(audit.get("revision"), str) or not audit.get("revision", "").strip():
            errors.append("$.audit.revision: expected a non-empty string or '[unknown]'")
        if audit.get("dirty_state") not in dirty_states:
            errors.append("$.audit.dirty_state: expected clean, dirty, or unknown")
        audit_date = audit.get("date")
        try:
            if not isinstance(audit_date, str):
                raise ValueError
            dt.date.fromisoformat(audit_date)
        except ValueError:
            errors.append("$.audit.date: expected a valid absolute YYYY-MM-DD date")
        if not _is_string_list(audit.get("commands")) or not audit.get("commands"):
            errors.append("$.audit.commands: expected a non-empty array of command strings")

    for key in ("scope", "generated_by"):
        if key in document and not isinstance(document[key], str):
            errors.append(f"$.{key}: expected a string")
    if not isinstance(document.get("scope"), str) or not document.get("scope", "").strip():
        errors.append("$.scope: expected a non-empty string")
    _validate_execution(
        document.get("execution"),
        prefix="$.execution",
        errors=errors,
        modes=explicit_list_modes,
        stderr_statuses=stderr_statuses,
    )
    _validate_explicit_list(
        document.get("limitations"),
        prefix="$.limitations",
        errors=errors,
        modes=explicit_list_modes,
    )
    # $.summary and its triage ledger: _validate_summary, defined after main().
    _validate_summary(document, errors=errors)

    # Top-level partition check, opt-in via execution.scan_roots: when scan
    # roots are declared, every immediate child of the audited root must be
    # covered by a scan root, named by a requested exclusion, or named by a
    # stated limitation.  Deliberately shallow: deeper recursive coverage
    # checks and the metric-echo cross-check (every metric.value must appear
    # in an observation) were measured and rejected as false-positive-prone.
    execution = document.get("execution")
    declared_scan_roots: list[str] = []
    if isinstance(execution, dict) and _is_string_list(execution.get("scan_roots")):
        declared_scan_roots = [
            scan_root
            for scan_root in execution["scan_roots"]
            if os.path.isabs(scan_root)
        ]
    if declared_scan_roots and repo_root is not None:
        exclusion_items: list[str] = []
        requested_exclusions = execution.get("requested_exclusions")
        if isinstance(requested_exclusions, dict) and _is_string_list(
            requested_exclusions.get("items")
        ):
            exclusion_items = list(requested_exclusions["items"])
        limitation_items: list[str] = []
        limitations = document.get("limitations")
        if isinstance(limitations, dict) and _is_string_list(limitations.get("items")):
            limitation_items = list(limitations["items"])
        if repo_root.is_dir():
            root_text = str(repo_root)
            for entry in sorted(os.listdir(root_text)):
                entry_path = os.path.join(root_text, entry)
                if any(
                    _path_covers(scan_root, entry_path)
                    or _path_covers(entry_path, scan_root)
                    for scan_root in declared_scan_roots
                ):
                    continue
                mention = re.compile(
                    r"(?<![\w.-])" + re.escape(entry) + r"(?![\w.-])"
                )
                if any(
                    mention.search(item)
                    for item in exclusion_items + limitation_items
                ):
                    continue
                errors.append(
                    f"$.execution.scan_roots: top-level entry {entry!r} is "
                    "neither scanned, excluded, nor a stated limitation"
                )
        elif require_existing_paths:
            errors.append(
                "$.execution.scan_roots: cannot verify the top-level partition "
                "because the audited root is not a directory"
            )

    findings = document.get("findings")
    if not isinstance(findings, list):
        errors.append("$.findings: expected an array")
        findings = []

    finding_schema = schema["$defs"]["finding"]
    required_finding = finding_schema["required"]
    allowed_finding = finding_schema["properties"]
    level_order = list(schema["x-claim-level-order"])
    level_index = {name: index for index, name in enumerate(level_order)}
    ceilings = schema["x-evidence-claim-ceilings"]
    behavioral_types = set(schema["x-behavioral-evidence"])

    seen_ids: set[str] = set()
    for index, finding in enumerate(findings):
        prefix = f"$.findings[{index}]"
        if not isinstance(finding, dict):
            errors.append(f"{prefix}: expected an object")
            continue

        finding_id = finding.get("id")
        if not isinstance(finding_id, str) or ID_PATTERN.fullmatch(finding_id) is None:
            errors.append(f"{prefix}.id: invalid finding identifier")
        elif finding_id in seen_ids:
            errors.append(f"{prefix}.id: duplicate finding identifier {finding_id!r}")
        else:
            seen_ids.add(finding_id)
        if isinstance(finding_id, str) and ID_PATTERN.fullmatch(finding_id) is not None:
            # Carry the author-visible finding id in every later message.
            prefix = f"[{finding_id}] $.findings[{index}]"

        _check_keys(
            finding,
            required=required_finding,
            allowed=allowed_finding,
            prefix=prefix,
            errors=errors,
        )

        artifact_class = finding.get("artifact_class")
        if artifact_class not in artifact_classes:
            errors.append(f"{prefix}.artifact_class: unsupported value {artifact_class!r}")
        claim_level = finding.get("claim_level")
        if claim_level not in claim_levels:
            errors.append(f"{prefix}.claim_level: unsupported value {claim_level!r}")
        claim = finding.get("claim")
        if not isinstance(claim, str) or not claim.strip():
            errors.append(f"{prefix}.claim: expected a non-empty string")
            claim = ""
        if finding.get("confidence") not in confidences:
            errors.append(f"{prefix}.confidence: unsupported value")
        if finding.get("severity") not in severities:
            errors.append(f"{prefix}.severity: unsupported value")
        disposition = finding.get("disposition")
        if disposition not in dispositions:
            errors.append(f"{prefix}.disposition: unsupported value {disposition!r}")
        for key in ("recommendation",):
            if not isinstance(finding.get(key), str) or not finding.get(key, "").strip():
                errors.append(f"{prefix}.{key}: expected a non-empty string")
        for key in (
            "meaningful_differences",
            "boundary_constraints",
            "affected_consumers",
            "owners",
            "public_boundaries",
            "missing_evidence",
            "assumptions",
            "exclusions",
        ):
            if not _is_string_list(finding.get(key)):
                errors.append(f"{prefix}.{key}: expected an array of strings")

        location_keys: set[
            Tuple[str, Optional[int], Optional[int], Optional[str], Optional[str]]
        ] = set()
        locations = finding.get("locations")
        if not isinstance(locations, list) or not locations:
            errors.append(f"{prefix}.locations: expected a non-empty array")
        else:
            for source_index, source in enumerate(locations):
                key = _validate_source(
                    source,
                    prefix=f"{prefix}.locations[{source_index}]",
                    errors=errors,
                    repo_root=repo_root,
                    require_existing_paths=require_existing_paths,
                    locator_kinds=locator_kinds,
                )
                if key is not None:
                    location_keys.add(key)

        observations = finding.get("observations")
        if not isinstance(observations, list) or not observations:
            errors.append(f"{prefix}.observations: expected a non-empty array")
        else:
            for observation_index, observation in enumerate(observations):
                observation_prefix = f"{prefix}.observations[{observation_index}]"
                if not isinstance(observation, dict):
                    errors.append(f"{observation_prefix}: expected an object")
                    continue
                _check_keys(
                    observation,
                    required=("detail", "command", "sources"),
                    allowed=("detail", "command", "sources"),
                    prefix=observation_prefix,
                    errors=errors,
                )
                for key in ("detail", "command"):
                    if not isinstance(observation.get(key), str) or not observation.get(key, "").strip():
                        errors.append(f"{observation_prefix}.{key}: expected a non-empty string")
                sources = observation.get("sources")
                if not isinstance(sources, list) or not sources:
                    errors.append(f"{observation_prefix}.sources: expected a non-empty array")
                else:
                    for source_index, source in enumerate(sources):
                        _validate_source(
                            source,
                            prefix=f"{observation_prefix}.sources[{source_index}]",
                            errors=errors,
                            repo_root=repo_root,
                            require_existing_paths=require_existing_paths,
                            locator_kinds=locator_kinds,
                        )

        evidence = finding.get("evidence")
        evidence_kinds: set[str] = set()
        evidence_ids: set[str] = set()
        authority_rule_kinds: dict[str, str] = {}
        max_ceiling = -1
        if not isinstance(evidence, list) or not evidence:
            errors.append(f"{prefix}.evidence: expected a non-empty array")
            evidence = []
        for evidence_index, item in enumerate(evidence):
            evidence_prefix = f"{prefix}.evidence[{evidence_index}]"
            if not isinstance(item, dict):
                errors.append(f"{evidence_prefix}: expected an object")
                continue
            _check_keys(
                item,
                required=("id", "type", "detail", "sources", "provenance", "limitations"),
                allowed=(
                    "id",
                    "type",
                    "detail",
                    "sources",
                    "provenance",
                    "limitations",
                    "authority_rule",
                    "metric",
                ),
                prefix=evidence_prefix,
                errors=errors,
            )
            evidence_type = item.get("type")
            evidence_id = item.get("id")
            if not isinstance(evidence_id, str) or re.fullmatch(r"E[1-9][0-9]*", evidence_id) is None:
                errors.append(f"{evidence_prefix}.id: expected E followed by a positive integer")
            elif evidence_id in evidence_ids:
                errors.append(f"{evidence_prefix}.id: duplicate evidence identifier {evidence_id!r}")
            else:
                evidence_ids.add(evidence_id)
            if evidence_type not in evidence_types:
                errors.append(f"{evidence_prefix}.type: unsupported value {evidence_type!r}")
            else:
                evidence_kinds.add(evidence_type)
                ceiling = ceilings.get(evidence_type)
                if ceiling in level_index:
                    max_ceiling = max(max_ceiling, level_index[ceiling])
            if not isinstance(item.get("detail"), str) or not item.get("detail", "").strip():
                errors.append(f"{evidence_prefix}.detail: expected a non-empty string")
            _validate_evidence_provenance(
                item.get("provenance"),
                prefix=f"{evidence_prefix}.provenance",
                errors=errors,
                kinds=provenance_kinds,
            )
            _validate_explicit_list(
                item.get("limitations"),
                prefix=f"{evidence_prefix}.limitations",
                errors=errors,
                modes=explicit_list_modes,
            )
            sources = item.get("sources")
            if not isinstance(sources, list) or not sources:
                errors.append(f"{evidence_prefix}.sources: expected a non-empty array")
            else:
                for source_index, source in enumerate(sources):
                    _validate_source(
                        source,
                        prefix=f"{evidence_prefix}.sources[{source_index}]",
                        errors=errors,
                        repo_root=repo_root,
                        require_existing_paths=require_existing_paths,
                        locator_kinds=locator_kinds,
                    )
            if "metric" in item:
                _validate_metric(item["metric"], prefix=f"{evidence_prefix}.metric", errors=errors)
            if evidence_type == "authority-rule":
                rule_kind = _validate_authority_rule(
                    item.get("authority_rule"),
                    prefix=f"{evidence_prefix}.authority_rule",
                    errors=errors,
                    kinds=authority_kind_values,
                    bases=authority_basis_values,
                )
                if isinstance(evidence_id, str) and rule_kind is not None:
                    authority_rule_kinds[evidence_id] = rule_kind
            elif "authority_rule" in item:
                errors.append(
                    f"{evidence_prefix}.authority_rule: allowed only for authority-rule evidence"
                )

        if claim_level in level_index and level_index[claim_level] > max_ceiling:
            errors.append(
                f"{prefix}.claim_level: {claim_level!r} exceeds the strongest "
                "declared evidence type"
            )
        behavior_wording = bool(BEHAVIOR_WORDING.search(claim))
        if behavior_wording and claim_level != "behavioral-equivalence":
            errors.append(
                f"{prefix}.claim: behavioral-equivalence wording requires "
                "claim_level 'behavioral-equivalence'"
            )
        if EXACT_IDENTITY_WORDING.search(claim) and not (
            evidence_kinds & EXACT_IDENTITY_EVIDENCE
        ):
            errors.append(
                f"{prefix}.claim: byte-identity wording requires "
                "exact-content-hash or asset-exact-hash evidence"
            )
        if claim_level == "behavioral-equivalence" and not (evidence_kinds & behavioral_types):
            errors.append(
                f"{prefix}.evidence: similarity or structure cannot establish behavioral "
                "equivalence; add differential-test, contract-test, or runtime-trace evidence"
            )
        if claim_level in {
            "lexical-similarity",
            "structural-similarity",
            "semantic-overlap",
            "behavioral-equivalence",
        } and len(location_keys) < 2:
            errors.append(f"{prefix}.locations: comparison claims require two distinct locations")

        squint = finding.get("squint")
        squint_statuses: dict[str, str] = {}
        squint_evidence_refs: dict[str, set[str]] = {}
        if not isinstance(squint, dict):
            errors.append(f"{prefix}.squint: expected an object")
        else:
            _check_keys(
                squint,
                required=("S", "Q", "U", "I", "N", "T"),
                allowed=("S", "Q", "U", "I", "N", "T"),
                prefix=f"{prefix}.squint",
                errors=errors,
            )
            for gate_id in ("S", "Q", "U", "I", "N", "T"):
                gate = squint.get(gate_id)
                gate_prefix = f"{prefix}.squint.{gate_id}"
                if not isinstance(gate, dict):
                    errors.append(f"{gate_prefix}: expected an object")
                    continue
                _check_keys(
                    gate,
                    required=("status", "rationale", "evidence_refs"),
                    allowed=("status", "rationale", "evidence_refs"),
                    prefix=gate_prefix,
                    errors=errors,
                )
                status = gate.get("status")
                if status not in squint_status_values:
                    errors.append(f"{gate_prefix}.status: expected pass, fail, or unknown")
                else:
                    squint_statuses[gate_id] = status
                if not isinstance(gate.get("rationale"), str) or not gate.get("rationale", "").strip():
                    errors.append(f"{gate_prefix}.rationale: expected a non-empty string")
                refs = gate.get("evidence_refs")
                if not isinstance(refs, list) or not all(isinstance(ref, str) for ref in refs):
                    errors.append(f"{gate_prefix}.evidence_refs: expected an array of evidence IDs")
                else:
                    if len(refs) != len(set(refs)):
                        errors.append(
                            f"{gate_prefix}.evidence_refs: duplicate values are forbidden"
                        )
                    squint_evidence_refs[gate_id] = set(refs)
                    missing_refs = sorted(set(refs) - evidence_ids)
                    if missing_refs:
                        errors.append(f"{gate_prefix}.evidence_refs: unknown IDs {missing_refs}")
                    if status in {"pass", "fail"} and not refs:
                        errors.append(f"{gate_prefix}.evidence_refs: pass/fail requires cited evidence")

        for risk_name in ("maintenance_risk", "change_risk"):
            risk = finding.get(risk_name)
            risk_prefix = f"{prefix}.{risk_name}"
            if not isinstance(risk, dict):
                errors.append(f"{risk_prefix}: expected an object")
            else:
                _check_keys(
                    risk,
                    required=("level", "rationale"),
                    allowed=("level", "rationale"),
                    prefix=risk_prefix,
                    errors=errors,
                )
                if risk.get("level") not in risk_levels:
                    errors.append(f"{risk_prefix}.level: unsupported risk level")
                if not isinstance(risk.get("rationale"), str) or not risk.get("rationale", "").strip():
                    errors.append(f"{risk_prefix}.rationale: expected a non-empty string")

        plan = finding.get("verification_plan")
        if not isinstance(plan, dict):
            errors.append(f"{prefix}.verification_plan: expected an object")
        else:
            _check_keys(
                plan,
                required=("steps", "unrun_checks"),
                allowed=("steps", "unrun_checks"),
                prefix=f"{prefix}.verification_plan",
                errors=errors,
            )
            steps = plan.get("steps")
            if not isinstance(steps, list) or not steps:
                errors.append(f"{prefix}.verification_plan.steps: expected a non-empty array")
            else:
                for step_index, step in enumerate(steps):
                    step_prefix = f"{prefix}.verification_plan.steps[{step_index}]"
                    if not isinstance(step, dict):
                        errors.append(f"{step_prefix}: expected an object")
                        continue
                    step_keys = (
                        "command",
                        "prerequisites",
                        "environment",
                        "fixtures",
                        "expected",
                        "failure_means",
                    )
                    _check_keys(
                        step,
                        required=step_keys,
                        allowed=step_keys,
                        prefix=step_prefix,
                        errors=errors,
                    )
                    for key in ("command", "environment", "expected", "failure_means"):
                        if not isinstance(step.get(key), str) or not step.get(key, "").strip():
                            errors.append(f"{step_prefix}.{key}: expected a non-empty string")
                    for key in ("prerequisites", "fixtures"):
                        if not _is_string_list(step.get(key)):
                            errors.append(f"{step_prefix}.{key}: expected an array of strings")
            if not _is_string_list(plan.get("unrun_checks")):
                errors.append(f"{prefix}.verification_plan.unrun_checks: expected an array of strings")

        rollback = finding.get("rollback")
        if not isinstance(rollback, dict):
            errors.append(f"{prefix}.rollback: expected an object")
        else:
            _check_keys(
                rollback,
                required=("boundary", "trigger", "steps"),
                allowed=("boundary", "trigger", "steps"),
                prefix=f"{prefix}.rollback",
                errors=errors,
            )
            for key in ("boundary", "trigger"):
                if not isinstance(rollback.get(key), str) or not rollback.get(key, "").strip():
                    errors.append(f"{prefix}.rollback.{key}: expected a non-empty string")
            if not _is_string_list(rollback.get("steps")) or not rollback.get("steps"):
                errors.append(f"{prefix}.rollback.steps: expected a non-empty array of strings")

        if "action" in finding:
            if finding["action"] not in actions:
                errors.append(f"{prefix}.action: unsupported value {finding['action']!r}")
            action_disposition = {
                "reuse-helper-or-component": "reuse-existing",
                "extract-local-abstraction": "extract",
                "parameterize-test": "extract",
                "centralize-source-of-truth": "centralize",
                "consolidate-dependency": "centralize",
                "generate-from-schema": "generate",
                "add-parity-test": "parity",
                "link-contracts-or-assets": "link-and-monitor",
                "no-change": "keep",
                "investigate": "needs-evidence",
            }
            expected_disposition = action_disposition.get(finding["action"])
            if expected_disposition != disposition:
                errors.append(
                    f"{prefix}.action: {finding['action']!r} requires disposition "
                    f"{expected_disposition!r}, not {disposition!r}"
                )
        if disposition == "reuse-existing" and "existing-abstraction" not in evidence_kinds:
            errors.append(f"{prefix}.disposition: reuse-existing requires existing-abstraction evidence")
        if finding.get("action") == "parameterize-test" and "test-setup-overlap" not in evidence_kinds:
            errors.append(f"{prefix}.action: parameterize-test requires test-setup-overlap evidence")
        if finding.get("action") == "consolidate-dependency" and "dependency-capability-overlap" not in evidence_kinds:
            errors.append(
                f"{prefix}.action: consolidate-dependency requires "
                "dependency-capability-overlap evidence"
            )
        action_dispositions = {
            "reuse-existing",
            "extract",
            "centralize",
            "generate",
        }
        if disposition in action_dispositions and not (
            {"boundary-analysis", "semantic-contract"} & evidence_kinds
        ):
            errors.append(
                f"{prefix}.disposition: action recommendations require boundary-analysis "
                "or semantic-contract evidence"
            )
        structural_required_gates = ("S", "Q", "I", "N", "T")
        if disposition in action_dispositions:
            failed = [gate for gate in structural_required_gates if squint_statuses.get(gate) != "pass"]
            if failed:
                errors.append(
                    f"{prefix}.disposition: {disposition} requires passed SQUINT gates "
                    f"{list(structural_required_gates)}; not passed: {failed}"
                )
        if disposition == "parity":
            for gate in ("S", "T"):
                if squint_statuses.get(gate) != "pass":
                    errors.append(f"{prefix}.disposition: parity requires SQUINT {gate}=pass")
            if "semantic-contract" not in evidence_kinds:
                errors.append(f"{prefix}.disposition: parity requires semantic-contract evidence")
        authority_kinds_by_disposition = {
            "centralize": {"authoritative-derivation", "shared-requirement"},
            "generate": {"authoritative-derivation"},
            "parity": {"explicit-parity-invariant", "shared-requirement"},
        }
        if disposition in authority_kinds_by_disposition:
            if squint_statuses.get("U") == "fail":
                errors.append(
                    f"{prefix}.disposition: {disposition} is unsafe when SQUINT U=fail"
                )
            eligible_authority_ids = {
                evidence_id
                for evidence_id, rule_kind in authority_rule_kinds.items()
                if rule_kind in authority_kinds_by_disposition[disposition]
            }
            if not eligible_authority_ids:
                errors.append(
                    f"{prefix}.disposition: {disposition} requires typed, cited authority-rule "
                    "evidence; ownership or maintenance responsibility alone is insufficient"
                )
            elif not (eligible_authority_ids & squint_evidence_refs.get("U", set())):
                errors.append(
                    f"{prefix}.squint.U.evidence_refs: must cite the applicable authority-rule "
                    f"evidence for {disposition}"
                )
        if disposition == "needs-evidence":
            if "unknown" not in set(squint_statuses.values()):
                errors.append(
                    f"{prefix}.disposition: needs-evidence requires at least one unknown SQUINT gate"
                )
            missing_evidence = finding.get("missing_evidence")
            if not isinstance(missing_evidence, list) or not missing_evidence:
                errors.append(
                    f"{prefix}.missing_evidence: needs-evidence requires at least one item"
                )
        if disposition == "keep" and "fail" not in set(squint_statuses.values()):
            errors.append(f"{prefix}.disposition: keep requires at least one failed SQUINT gate")

    if errors:
        raise FindingsValidationError(errors)
    return document


def _write_exclusive_or_verify(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    except FileExistsError:
        if path.read_bytes() != payload:
            raise FindingsValidationError((f"{path}: refuses to overwrite different content",))
        return
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(payload)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate evidence-backed Abstraction Police findings."
    )
    parser.add_argument("findings", type=Path, help="JSON findings document")
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    parser.add_argument("--repo-root", type=Path)
    path_group = parser.add_mutually_exclusive_group()
    path_group.add_argument(
        "--require-existing-paths",
        action="store_true",
        dest="require_existing_paths",
        help="Require every cited filesystem path to exist (default)",
    )
    path_group.add_argument(
        "--allow-missing-paths",
        action="store_false",
        dest="require_existing_paths",
        help="Allow archived findings whose cited files are no longer materialized",
    )
    parser.set_defaults(require_existing_paths=True)
    parser.add_argument(
        "--canonical-out",
        help="Write canonical JSON to this new path, or '-' for stdout",
    )
    parser.add_argument("--quiet", action="store_true")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        schema = load_json(args.schema)
        if not isinstance(schema, dict):
            raise FindingsValidationError((f"{args.schema}: schema must be an object",))
        document = validate_document(
            load_json(args.findings),
            schema=schema,
            repo_root=args.repo_root,
            require_existing_paths=args.require_existing_paths,
        )
        canonical = canonical_json_bytes(document)
        if args.canonical_out == "-":
            sys.stdout.buffer.write(canonical)
        elif args.canonical_out:
            _write_exclusive_or_verify(Path(args.canonical_out), canonical)
        elif not args.quiet:
            print(f"valid: {len(document['findings'])} finding(s)")
        return 0
    except FindingsValidationError as exc:
        for error in exc.errors:
            print(f"ERROR {error}", file=sys.stderr)
        return 1


def _validate_summary(document: Mapping[str, Any], *, errors: list[str]) -> None:
    """Validate ``$.summary`` and its triage ledger (SKILL.md step 4).

    Deliberately defined after ``main``: ``references/validator-rules.md``
    cites this file by line number, and appending keeps every earlier
    citation stable.  The ledger arithmetic follows the step-4 definitions:
    every candidate ends promoted, dropped-with-class, or not-reached, so
    ``dropped_by_class + promoted + not_reached`` must equal
    ``candidates_total``.
    """

    summary = document.get("summary")
    if not isinstance(summary, dict):
        errors.append("$.summary: expected an object")
        return
    _check_keys(
        summary, required=("triage",), allowed=("triage",), prefix="$.summary", errors=errors
    )
    triage = summary.get("triage")
    if not isinstance(triage, dict):
        errors.append("$.summary.triage: expected an object")
        return
    prefix = "$.summary.triage"
    count_keys = ("candidates_total", "investigated", "promoted", "not_reached")
    map_keys = ("candidates_by_kind", "dropped_by_class")
    _check_keys(
        triage,
        required=count_keys + map_keys,
        allowed=count_keys + map_keys,
        prefix=prefix,
        errors=errors,
    )
    counts: dict[str, int] = {}
    for key in count_keys:
        value = triage.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            errors.append(f"{prefix}.{key}: expected a non-negative integer")
        else:
            counts[key] = value
    totals: dict[str, int] = {}
    for key in map_keys:
        value = triage.get(key)
        if not isinstance(value, dict):
            errors.append(
                f"{prefix}.{key}: expected an object mapping class names to "
                "non-negative integers"
            )
            continue
        valid = True
        for name in sorted(value):
            count = value[name]
            if not name.strip():
                errors.append(f"{prefix}.{key}: empty class name")
                valid = False
            if isinstance(count, bool) or not isinstance(count, int) or count < 0:
                errors.append(f"{prefix}.{key}.{name}: expected a non-negative integer")
                valid = False
        if valid:
            totals[key] = sum(value.values())
    if len(counts) == len(count_keys) and len(totals) == len(map_keys):
        total = counts["candidates_total"]
        if totals["candidates_by_kind"] != total:
            errors.append(
                f"{prefix}.candidates_by_kind: values sum to "
                f"{totals['candidates_by_kind']}, expected candidates_total {total}"
            )
        if counts["promoted"] > counts["investigated"]:
            errors.append(
                f"{prefix}.promoted: {counts['promoted']} exceeds investigated "
                f"{counts['investigated']}"
            )
        if counts["investigated"] + counts["not_reached"] > total:
            errors.append(
                f"{prefix}: investigated + not_reached exceeds candidates_total {total}"
            )
        ledger = totals["dropped_by_class"] + counts["promoted"] + counts["not_reached"]
        if ledger != total:
            errors.append(
                f"{prefix}: dropped_by_class + promoted + not_reached is {ledger}, "
                f"expected candidates_total {total}"
            )
    not_reached = counts.get("not_reached", 0)
    if not_reached > 0:
        limitations = document.get("limitations")
        items = limitations.get("items") if isinstance(limitations, dict) else None
        named = False
        if (
            isinstance(limitations, dict)
            and limitations.get("mode") == "specified"
            and _is_string_list(items)
        ):
            phrase = re.compile(r"\bnot[ -]reached\b", re.IGNORECASE)
            count = re.compile(r"(?<![\d.])" + str(not_reached) + r"(?![\d.])")
            named = any(phrase.search(item) and count.search(item) for item in items)
        if not named:
            errors.append(
                f"{prefix}.not_reached: {not_reached} candidate(s) not reached, so "
                "$.limitations.items must contain an item with the phrase "
                "'not reached' and that count"
            )


if __name__ == "__main__":
    raise SystemExit(main())
