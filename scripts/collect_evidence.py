#!/usr/bin/env python3
"""Collect deterministic, candidate-only abstraction evidence from a repository.

The scanner intentionally stops before deciding whether repeated artifacts should
share an abstraction. Its output is suitable for a later contextual review.

Determinism contract: given identical inputs and identical scanner bytes, two
runs must produce byte-identical stdout. All iteration is sorted; no absolute
filesystem paths are ever emitted (only root-relative posix paths and, for
multiple roots, a deterministic argument-order index prefix). Symbolic links are
never followed; every skipped link is disclosed in scan.skipped_symlinks.
"""

import argparse
import fnmatch
import hashlib
import json
import os
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Any, DefaultDict, Dict, Iterable, List, Optional, Sequence, Set, Tuple


SCHEMA_VERSION = "1.2"
SCANNER_VERSION = "1.2.0"
NOTICE = (
    "Candidate evidence only. Similarity does not establish a shared abstraction "
    "or a safe refactor."
)

IGNORED_DIRECTORY_NAMES = {
    ".cache",
    ".git",
    ".gradle",
    ".hg",
    ".idea",
    ".mypy_cache",
    ".next",
    ".nuxt",
    ".parcel-cache",
    ".pytest_cache",
    ".ruff_cache",
    ".svelte-kit",
    ".svn",
    ".terraform",
    ".tox",
    ".turbo",
    ".venv",
    ".yarn",
    "__pycache__",
    "build",
    "carthage",
    "coverage",
    "deriveddata",
    "dist",
    "env",
    "generated",
    "node_modules",
    "out",
    "pods",
    "target",
    "third-party",
    "third_party",
    "vendor",
    "vendors",
    "venv",
    "xcuserdata",
}

IGNORED_FILE_NAMES = {
    ".ds_store",
    ".git",
    "cargo.lock",
    "composer.lock",
    "package-lock.json",
    "pnpm-lock.yaml",
    "poetry.lock",
    "yarn.lock",
}

LITERAL_EXTENSIONS = {
    ".bash",
    ".c",
    ".cfg",
    ".conf",
    ".cpp",
    ".cs",
    ".css",
    ".fish",
    ".go",
    ".h",
    ".hpp",
    ".htm",
    ".html",
    ".ini",
    ".java",
    ".js",
    ".json",
    ".jsx",
    ".kt",
    ".kts",
    ".less",
    ".m",
    ".md",
    ".mdx",
    ".mm",
    ".php",
    ".py",
    ".rb",
    ".rs",
    ".sass",
    ".scss",
    ".sh",
    ".sql",
    ".svelte",
    ".swift",
    ".toml",
    ".ts",
    ".tsx",
    ".vue",
    ".yaml",
    ".yml",
    ".zsh",
}

DOCUMENT_EXTENSIONS = {".adoc", ".htm", ".html", ".md", ".mdx", ".rst", ".txt"}

# Structured data and prose formats are excluded from token-block clone
# detection: after identifier/literal abstraction their token streams collapse
# to format boilerplate (every asset-catalog JSON would "clone" every other).
TOKEN_CLONE_EXCLUDED_EXTENSIONS = DOCUMENT_EXTENSIONS | {
    ".cfg",
    ".conf",
    ".ini",
    ".json",
    ".toml",
    ".yaml",
    ".yml",
}

QUOTED_LITERAL_PATTERNS = (
    ('"', re.compile(r'"(?P<value>(?:\\.|[^"\\])*)"')),
    ("'", re.compile(r"'(?P<value>(?:\\.|[^'\\])*)'")),
    ("`", re.compile(r"`(?P<value>(?:\\.|[^`\\])*)`")),
)

CSS_FONT_FAMILY_PATTERN = re.compile(
    r"\bfont-family\b\s*:\s*(?P<value>[^;}\n]+)", re.IGNORECASE
)
PROPERTY_FONT_FAMILY_PATTERN = re.compile(
    r"(?:[\"']?fontFamily[\"']?)\s*:\s*(?P<quote>[\"'])(?P<value>.*?)(?P=quote)",
    re.IGNORECASE,
)

COMMENT_LINE_PATTERN = re.compile(r"^\s*(?:///|//|#|\*|--|<!--)")

# Lexical shape classes for repeated_literal candidates. First match wins, so
# order is load-bearing: e.g. "checkmark.circle.fill" matches both
# dotted-identifier and reverse-dns, and must classify as dotted-identifier.
SHAPE_CLASSES = (
    ("url", re.compile(r"^[a-z][a-z0-9+.-]*://\S+$"), False),
    ("mime-type", re.compile(r"^[a-z]+/[a-z0-9.+-]+$"), False),
    ("dotted-identifier", re.compile(r"^[a-z0-9]+(?:\.[a-z0-9]+){1,}$"), False),
    ("reverse-dns", re.compile(r"^(?:[a-z][a-z0-9]*\.){2,}[a-z0-9.]+$"), False),
    (
        "path-like",
        re.compile(r"^[A-Za-z0-9_.@${}\[\]-]+(?:/[A-Za-z0-9_.@${}\[\]*-]+)+$"),
        False,
    ),
    (
        "symbol-path",
        re.compile(r"^[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)+(?:\(\))?$"),
        False,
    ),
    ("identifier-token", re.compile(r"^[A-Za-z_$][A-Za-z0-9_$]*$"), False),
    ("regex-like", re.compile(r"(\\[dwsbDWSB]|\[\^|\(\?:|\{\d+,?\d*\})"), True),
    ("format-fragment", re.compile(r"\\\(|\$\{|\{[a-z_][\w.]*\}|%[sd@]"), True),
)

# A quoted literal counts as a mapping key only when it is in key POSITION:
# followed by a colon AND preceded (after removing complete quoted spans) by
# structural characters only. This keeps ternary first branches and
# `case "...":` labels that a trailing-colon-only test silently dropped.
MAPPING_KEY_PREFIX_PATTERN = re.compile(r"^[\s\-\{\[,:0-9.]*$")

# --- token_block_clone tokenizer (language-agnostic, Type-2) ---------------
TOKEN_PATTERN = re.compile(
    r"""(?P<str>"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|`(?:\\.|[^`\\])*`)
      | (?P<num>\b\d+(?:\.\d+)?\b)
      | (?P<ident>[A-Za-z_$][A-Za-z_$0-9]*)
      | (?P<punct>[^\s])""",
    re.VERBOSE,
)
BLOCK_COMMENT_PATTERN = re.compile(r"/\*.*?\*/", re.S)
SLASH_COMMENT_PATTERN = re.compile(r"//.*$")
HASH_COMMENT_PATTERN = re.compile(r"(?<!['\"])#.*$")
HASH_COMMENT_SUFFIXES = {".bash", ".fish", ".py", ".rb", ".sh", ".zsh"}

# Detector registry.
# Language-specific AST detectors were evaluated and rejected: this scanner
# audits arbitrary trees and must not privilege one language; see build record.
KIND_ORDER = {
    "exact_file": 0,
    "repeated_literal": 1,
    "font_family": 2,
    "normalized_text_block": 3,
    "json_key_shape": 4,
    "token_block_clone": 5,
}

CLAIMS = {
    "exact_file": "Files have byte-identical content.",
    "repeated_literal": "Artifacts contain the same normalized literal.",
    "font_family": "Artifacts declare the same normalized font-family value.",
    "normalized_text_block": (
        "Documents contain the same whitespace- and case-normalized text block."
    ),
    "json_key_shape": (
        "JSON objects have the same recursive key-and-value-type shape."
    ),
    "token_block_clone": (
        "Artifacts contain a contiguous run of identically shaped normalized "
        "tokens (identifiers, string values, and numbers erased)."
    ),
}

CLAIM_CEILINGS = {
    "exact_file": "lexical-similarity",
    "repeated_literal": "lexical-similarity",
    "font_family": "lexical-similarity",
    "normalized_text_block": "lexical-similarity",
    "json_key_shape": "structural-similarity",
    # A grammarless tokenizer proves token-shape identity only; the findings
    # schema maps token-similarity evidence to the lexical band.
    "token_block_clone": "lexical-similarity",
}


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def stable_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def normalize_space(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value)
    return re.sub(r"\s+", " ", normalized).strip()


def normalize_text_block(value: str) -> str:
    return normalize_space(value).casefold()


def normalize_font_family(value: str) -> str:
    normalized = normalize_space(value).strip().rstrip(",")
    normalized = normalized.replace('"', "").replace("'", "")
    normalized = re.sub(r"\s*,\s*", ",", normalized)
    return normalized.casefold()


def scanner_identity() -> Dict[str, str]:
    return {
        "sha256": sha256_bytes(Path(__file__).resolve().read_bytes()),
        "version": SCANNER_VERSION,
    }


def should_ignore_file(name: str) -> bool:
    lower_name = name.casefold()
    if lower_name in IGNORED_FILE_NAMES:
        return True
    if lower_name.endswith((".map", ".min.css", ".min.js")):
        return True
    if ".generated." in lower_name or lower_name.endswith(".g.dart"):
        return True
    return False


def directory_matches_exclude(rel_dir: str, exclude_globs: Sequence[str]) -> bool:
    for glob in exclude_globs:
        if fnmatch.fnmatchcase(rel_dir, glob):
            return True
        if glob.endswith("/*") and fnmatch.fnmatchcase(rel_dir, glob[:-2]):
            return True
    return False


def discover_files(
    root: Path,
    excluded_path: Optional[Path],
    exclude_globs: Sequence[str],
) -> Tuple[List[Path], List[str], List[str]]:
    """Walk one root; return (files, pruned nested-git rel paths, skipped symlink rel paths).

    Any directory BELOW the root that contains a `.git` entry (file or
    directory) is a nested repository, submodule, or git worktree checkout and
    is pruned whole. The root itself is never pruned. Symbolic links, to files
    or to directories, are never followed. Pruned paths and skipped links are
    disclosed so the scan boundary stays explicit.
    """
    files: List[Path] = []
    pruned: List[str] = []
    symlinks: List[str] = []
    for current_root, directory_names, file_names in os.walk(str(root), topdown=True):
        current = Path(current_root)
        kept_names: List[str] = []
        for name in sorted(directory_names):
            if name.casefold() in IGNORED_DIRECTORY_NAMES:
                continue
            child = current / name
            rel_dir = child.relative_to(root).as_posix()
            if child.is_symlink():
                symlinks.append(rel_dir)
                continue
            if (child / ".git").exists():
                pruned.append(rel_dir)
                continue
            if directory_matches_exclude(rel_dir, exclude_globs):
                continue
            kept_names.append(name)
        directory_names[:] = kept_names
        for file_name in sorted(file_names):
            if should_ignore_file(file_name):
                continue
            path = current / file_name
            rel_path = path.relative_to(root).as_posix()
            if path.is_symlink():
                symlinks.append(rel_path)
                continue
            if not path.is_file():
                continue
            if any(fnmatch.fnmatchcase(rel_path, glob) for glob in exclude_globs):
                continue
            if excluded_path is not None and path.resolve() == excluded_path:
                continue
            files.append(path)
    return files, sorted(pruned), sorted(symlinks)


def relative_path(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def decode_text(data: bytes) -> Optional[str]:
    if b"\x00" in data:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


def occurrence_sort_key(occurrence: Dict[str, Any]) -> Tuple[Any, ...]:
    return (
        occurrence.get("path", ""),
        occurrence.get("line", 0),
        occurrence.get("start_line", 0),
        occurrence.get("json_pointer", ""),
        occurrence.get("byte_size", 0),
    )


def unique_occurrences(occurrences: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    by_key: Dict[str, Dict[str, Any]] = {}
    for occurrence in occurrences:
        key = json.dumps(occurrence, ensure_ascii=False, sort_keys=True)
        by_key[key] = occurrence
    return sorted(by_key.values(), key=occurrence_sort_key)


def spans_multiple_artifacts(occurrences: Sequence[Dict[str, Any]]) -> bool:
    return len({occurrence["path"] for occurrence in occurrences}) >= 2


def candidate_identity(kind: str, normalized_key: str) -> Tuple[str, str]:
    fingerprint_value = sha256_bytes(normalized_key.encode("utf-8"))
    candidate_id = kind + ":" + sha256_bytes(
        (kind + "\x00" + fingerprint_value).encode("utf-8")
    )[:16]
    return "sha256:" + fingerprint_value, candidate_id


def candidate(
    kind: str,
    normalized_key: str,
    occurrences: Iterable[Dict[str, Any]],
    details: Dict[str, Any],
) -> Dict[str, Any]:
    fingerprint, candidate_id = candidate_identity(kind, normalized_key)
    ordered = unique_occurrences(occurrences)
    enriched = dict(details)
    enriched["distinct_file_count"] = len(
        {occurrence["path"] for occurrence in ordered}
    )
    enriched["occurrence_count"] = len(ordered)
    return {
        "candidate_id": candidate_id,
        "claim": CLAIMS[kind],
        "details": enriched,
        "claim_ceiling": CLAIM_CEILINGS[kind],
        "fingerprint": fingerprint,
        "kind": kind,
        "occurrences": ordered,
    }


def candidate_sort_key(item: Dict[str, Any]) -> Tuple[Any, ...]:
    details = item["details"]
    if item["kind"] == "token_block_clone":
        first_path = item["occurrences"][0]["path"] if item["occurrences"] else ""
        return (
            KIND_ORDER[item["kind"]],
            -details["token_count"],
            first_path,
            item["fingerprint"],
            item["candidate_id"],
        )
    return (
        KIND_ORDER[item["kind"]],
        -details["distinct_file_count"],
        -details["occurrence_count"],
        item["fingerprint"],
        item["candidate_id"],
    )


def collect_exact_file_candidates(
    file_records: Sequence[Tuple[Path, str, bytes, Optional[str]]]
) -> List[Dict[str, Any]]:
    groups: DefaultDict[str, List[Dict[str, Any]]] = defaultdict(list)
    sizes: Dict[str, int] = {}
    for _path, rel_path, data, _text in file_records:
        if not data:
            continue
        digest = sha256_bytes(data)
        groups[digest].append({"byte_size": len(data), "path": rel_path})
        sizes[digest] = len(data)

    results: List[Dict[str, Any]] = []
    for digest in sorted(groups):
        occurrences = unique_occurrences(groups[digest])
        if not spans_multiple_artifacts(occurrences):
            continue
        results.append(
            candidate(
                "exact_file",
                digest,
                occurrences,
                {"byte_size": sizes[digest], "content_sha256": digest},
            )
        )
    return results


def is_mapping_key(line: str, match_start: int, match_end: int) -> bool:
    if not line[match_end:].lstrip().startswith(":"):
        return False
    prefix = line[:match_start]
    for _quote, pattern in QUOTED_LITERAL_PATTERNS:
        prefix = pattern.sub("", prefix)
    return MAPPING_KEY_PREFIX_PATTERN.match(prefix) is not None


def classify_literal_shape(value: str) -> str:
    for name, pattern, use_search in SHAPE_CLASSES:
        found = pattern.search(value) if use_search else pattern.match(value)
        if found:
            return name
    return "prose-or-other"


def literal_truncation_risk(value: str) -> bool:
    """Unbalanced interpolation opens signal a fragment cut mid-string."""
    if value.count("\\(") > value.count(")"):
        return True
    if value.count("${") > value.count("}"):
        return True
    return False


def collect_literal_candidates(
    file_records: Sequence[Tuple[Path, str, bytes, Optional[str]]],
    min_literal_length: int,
) -> List[Dict[str, Any]]:
    groups: DefaultDict[str, List[Dict[str, Any]]] = defaultdict(list)
    apostrophe_risk: DefaultDict[str, bool] = defaultdict(bool)
    for path, rel_path, _data, text in file_records:
        if text is None or path.suffix.casefold() not in LITERAL_EXTENSIONS:
            continue
        for line_number, line in enumerate(text.splitlines(), start=1):
            line_is_comment = bool(COMMENT_LINE_PATTERN.match(line))
            for quote, pattern in QUOTED_LITERAL_PATTERNS:
                for match in pattern.finditer(line):
                    if is_mapping_key(line, match.start(), match.end()):
                        continue
                    normalized = normalize_space(match.group("value"))
                    if len(normalized) < min_literal_length:
                        continue
                    groups[normalized].append(
                        {
                            "line": line_number,
                            "line_is_comment": line_is_comment,
                            "path": rel_path,
                        }
                    )
                    if quote == "'":
                        before = line[match.start() - 1] if match.start() > 0 else ""
                        after = line[match.end():match.end() + 1]
                        if (
                            before.isalnum()
                            or before == "_"
                            or after.isalnum()
                            or after == "_"
                        ):
                            apostrophe_risk[normalized] = True

    results: List[Dict[str, Any]] = []
    for normalized in sorted(groups):
        occurrences = unique_occurrences(groups[normalized])
        if not spans_multiple_artifacts(occurrences):
            continue
        truncation = literal_truncation_risk(normalized)
        results.append(
            candidate(
                "repeated_literal",
                normalized,
                occurrences,
                {
                    "character_count": len(normalized),
                    "comment_only": all(
                        occurrence["line_is_comment"] for occurrence in occurrences
                    ),
                    "normalized_literal": normalized,
                    "normalization": (
                        "Unicode NFKC and collapsed whitespace; the value is a "
                        "regex-delimited fragment and may not be the complete "
                        "source literal"
                    ),
                    "shape_class": classify_literal_shape(normalized),
                    "truncation_risk": truncation,
                    "verbatim_at_source": not (
                        truncation or apostrophe_risk[normalized]
                    ),
                },
            )
        )
    return results


def collect_font_family_candidates(
    file_records: Sequence[Tuple[Path, str, bytes, Optional[str]]]
) -> List[Dict[str, Any]]:
    groups: DefaultDict[str, List[Dict[str, Any]]] = defaultdict(list)
    for path, rel_path, _data, text in file_records:
        if text is None or path.suffix.casefold() not in LITERAL_EXTENSIONS:
            continue
        for line_number, line in enumerate(text.splitlines(), start=1):
            for pattern in (CSS_FONT_FAMILY_PATTERN, PROPERTY_FONT_FAMILY_PATTERN):
                for match in pattern.finditer(line):
                    normalized = normalize_font_family(match.group("value"))
                    if not normalized:
                        continue
                    groups[normalized].append(
                        {"line": line_number, "path": rel_path}
                    )

    results: List[Dict[str, Any]] = []
    for normalized in sorted(groups):
        occurrences = unique_occurrences(groups[normalized])
        if not spans_multiple_artifacts(occurrences):
            continue
        results.append(
            candidate(
                "font_family",
                normalized,
                occurrences,
                {
                    "normalized_font_family": normalized,
                    "normalization": "case-folded, quote-free comma-separated family list",
                },
            )
        )
    return results


def paragraph_blocks(text: str) -> Iterable[Tuple[int, str]]:
    lines = text.splitlines()
    block_lines: List[str] = []
    start_line = 1
    for line_number, line in enumerate(lines, start=1):
        if line.strip():
            if not block_lines:
                start_line = line_number
            block_lines.append(line)
        elif block_lines:
            yield start_line, "\n".join(block_lines)
            block_lines = []
    if block_lines:
        yield start_line, "\n".join(block_lines)


def collect_text_block_candidates(
    file_records: Sequence[Tuple[Path, str, bytes, Optional[str]]],
    min_text_block_chars: int,
) -> List[Dict[str, Any]]:
    groups: DefaultDict[str, List[Dict[str, Any]]] = defaultdict(list)
    for path, rel_path, _data, text in file_records:
        if text is None or path.suffix.casefold() not in DOCUMENT_EXTENSIONS:
            continue
        for line_number, block in paragraph_blocks(text):
            normalized = normalize_text_block(block)
            if len(normalized) < min_text_block_chars:
                continue
            groups[normalized].append({"line": line_number, "path": rel_path})

    results: List[Dict[str, Any]] = []
    for normalized in sorted(groups):
        occurrences = unique_occurrences(groups[normalized])
        if not spans_multiple_artifacts(occurrences):
            continue
        results.append(
            candidate(
                "normalized_text_block",
                normalized,
                occurrences,
                {
                    "character_count": len(normalized),
                    "normalization": "Unicode NFKC, case-folded, collapsed whitespace",
                    "normalized_text": normalized,
                },
            )
        )
    return results


def json_value_shape(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return {
            "properties": {
                str(key): json_value_shape(value[key]) for key in sorted(value)
            },
            "type": "object",
        }
    if isinstance(value, list):
        unique_item_shapes: Dict[str, Dict[str, Any]] = {}
        for item in value:
            shape = json_value_shape(item)
            key = json.dumps(shape, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            unique_item_shapes[key] = shape
        return {
            "item_shapes": [unique_item_shapes[key] for key in sorted(unique_item_shapes)],
            "type": "array",
        }
    if value is None:
        return {"type": "null"}
    if isinstance(value, bool):
        return {"type": "boolean"}
    if isinstance(value, (int, float)):
        return {"type": "number"}
    if isinstance(value, str):
        return {"type": "string"}
    return {"type": type(value).__name__}


def escape_json_pointer_token(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")


def walk_json_objects(value: Any, pointer: str = "") -> Iterable[Tuple[str, Dict[str, Any]]]:
    if isinstance(value, dict):
        if len(value) >= 2:
            yield pointer or "/", json_value_shape(value)
        for key in sorted(value):
            child_pointer = pointer + "/" + escape_json_pointer_token(str(key))
            yield from walk_json_objects(value[key], child_pointer)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from walk_json_objects(item, pointer + "/" + str(index))


def collect_json_shape_candidates(
    file_records: Sequence[Tuple[Path, str, bytes, Optional[str]]]
) -> Tuple[List[Dict[str, Any]], List[str]]:
    groups: DefaultDict[str, List[Dict[str, Any]]] = defaultdict(list)
    shapes: Dict[str, Dict[str, Any]] = {}
    parse_errors: List[str] = []
    for path, rel_path, _data, text in file_records:
        if text is None or path.suffix.casefold() != ".json":
            continue
        try:
            value = json.loads(text)
        except (json.JSONDecodeError, UnicodeDecodeError):
            parse_errors.append(rel_path)
            continue
        for pointer, shape in walk_json_objects(value):
            canonical = json.dumps(
                shape, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            )
            groups[canonical].append({"json_pointer": pointer, "path": rel_path})
            shapes[canonical] = shape

    kept: List[Tuple[str, List[Dict[str, Any]]]] = []
    for canonical in sorted(groups):
        occurrences = unique_occurrences(groups[canonical])
        if not spans_multiple_artifacts(occurrences):
            continue
        kept.append((canonical, occurrences))

    ids: Dict[str, str] = {}
    filesets: Dict[str, frozenset] = {}
    for canonical, occurrences in kept:
        _fingerprint, kept_id = candidate_identity("json_key_shape", canonical)
        ids[canonical] = kept_id
        filesets[canonical] = frozenset(
            occurrence["path"] for occurrence in occurrences
        )

    # Subsumption is a LABEL, never a suppression: a shape is subsumed when its
    # file-set is a subset of a parent shape's file-set and its canonical form
    # is a substring (nested sub-object) of the parent's canonical form. The
    # nested shape genuinely was observed, so it stays in the output.
    subsumed_by: Dict[str, str] = {}
    for canonical, _occurrences in kept:
        parents = [
            other
            for other, _other_occurrences in kept
            if other != canonical
            and canonical in other
            and filesets[canonical] <= filesets[other]
        ]
        if parents:
            parents.sort(key=lambda value: (len(value), value))
            subsumed_by[canonical] = parents[0]
    subsumes: DefaultDict[str, List[str]] = defaultdict(list)
    for child in sorted(subsumed_by):
        subsumes[subsumed_by[child]].append(ids[child])

    results: List[Dict[str, Any]] = []
    for canonical, occurrences in kept:
        basenames = sorted(
            {occurrence["path"].rsplit("/", 1)[-1] for occurrence in occurrences}
        )
        results.append(
            candidate(
                "json_key_shape",
                canonical,
                occurrences,
                {
                    "basename_set": basenames,
                    "basename_uniform": len(basenames) == 1,
                    "normalization": "sorted keys with recursive JSON value types",
                    "shape": shapes[canonical],
                    "subsumed_by": (
                        ids[subsumed_by[canonical]]
                        if canonical in subsumed_by
                        else None
                    ),
                    "subsumes": sorted(subsumes.get(canonical, [])),
                },
            )
        )
    return results, sorted(parse_errors)


def _blank_preserving_newlines(match: "re.Match") -> str:
    return re.sub(r"[^\n]", " ", match.group(0))


def tokenize_for_clones(text: str, suffix: str) -> List[Tuple[str, int]]:
    text = BLOCK_COMMENT_PATTERN.sub(_blank_preserving_newlines, text)
    tokens: List[Tuple[str, int]] = []
    strip_hash = suffix in HASH_COMMENT_SUFFIXES
    for line_number, line in enumerate(text.splitlines(), start=1):
        line = SLASH_COMMENT_PATTERN.sub("", line)
        if strip_hash:
            line = HASH_COMMENT_PATTERN.sub("", line)
        for match in TOKEN_PATTERN.finditer(line):
            group = match.lastgroup
            if group == "str":
                token = "STR"
            elif group == "num":
                token = "NUM"
            elif group == "ident":
                token = "ID"
            else:
                token = match.group()
            tokens.append((token, line_number))
    return tokens


def _find_root(parent: List[int], index: int) -> int:
    while parent[index] != index:
        parent[index] = parent[parent[index]]
        index = parent[index]
    return index


def collect_token_clone_candidates(
    file_records: Sequence[Tuple[Path, str, bytes, Optional[str]]],
    min_clone_tokens: int,
) -> List[Dict[str, Any]]:
    """Language-agnostic Type-2 token-block clone detector.

    Fixed window of `min_clone_tokens` normalized tokens, stride 1; windows
    hashed and kept when >= 2 distinct files share a hash; contiguous matched
    offsets merged into maximal runs; runs clustered by union-find over shared
    window hashes. Byte-identical duplicate files are collapsed to one
    representative first, so exact_file groups are not re-reported as clones.
    """
    window = min_clone_tokens
    file_tokens: Dict[str, List[Tuple[str, int]]] = {}
    seen_digests: Set[str] = set()
    for path, rel_path, data, text in file_records:
        if text is None:
            continue
        suffix = path.suffix.casefold()
        if suffix not in LITERAL_EXTENSIONS or suffix in TOKEN_CLONE_EXCLUDED_EXTENSIONS:
            continue
        digest = sha256_bytes(data)
        if digest in seen_digests:
            continue
        seen_digests.add(digest)
        tokens = tokenize_for_clones(text, suffix)
        if len(tokens) >= window:
            file_tokens[rel_path] = tokens

    index: DefaultDict[str, List[Tuple[str, int]]] = defaultdict(list)
    for rel_path in sorted(file_tokens):
        token_values = [token for token, _line in file_tokens[rel_path]]
        for offset in range(len(token_values) - window + 1):
            digest = hashlib.blake2b(
                "\x00".join(token_values[offset:offset + window]).encode("utf-8"),
                digest_size=16,
            ).hexdigest()
            index[digest].append((rel_path, offset))

    shared: Dict[str, List[Tuple[str, int]]] = {
        digest: occ
        for digest, occ in index.items()
        if len({rel_path for rel_path, _offset in occ}) >= 2
    }

    matched_offsets: DefaultDict[str, Set[int]] = defaultdict(set)
    for digest in shared:
        for rel_path, offset in shared[digest]:
            matched_offsets[rel_path].add(offset)

    runs: List[Tuple[str, int, int]] = []
    run_ids: Dict[Tuple[str, int], int] = {}
    for rel_path in sorted(matched_offsets):
        offsets = sorted(matched_offsets[rel_path])
        start = previous = offsets[0]
        for offset in offsets[1:] + [None]:
            if offset is not None and offset == previous + 1:
                previous = offset
                continue
            run_index = len(runs)
            runs.append((rel_path, start, previous))
            for covered in range(start, previous + 1):
                run_ids[(rel_path, covered)] = run_index
            if offset is None:
                break
            start = previous = offset

    parent = list(range(len(runs)))
    for digest in sorted(shared):
        member_ids = sorted(
            {run_ids[(rel_path, offset)] for rel_path, offset in shared[digest]}
        )
        anchor = member_ids[0]
        for other in member_ids[1:]:
            root_a = _find_root(parent, anchor)
            root_b = _find_root(parent, other)
            if root_a != root_b:
                parent[max(root_a, root_b)] = min(root_a, root_b)

    clusters: DefaultDict[int, List[Tuple[str, int, int]]] = defaultdict(list)
    for run_index, run in enumerate(runs):
        clusters[_find_root(parent, run_index)].append(run)

    results: List[Dict[str, Any]] = []
    for cluster_root in sorted(clusters):
        members = clusters[cluster_root]
        if len({rel_path for rel_path, _start, _last in members}) < 2:
            continue
        occurrences: List[Dict[str, Any]] = []
        best: Optional[Tuple[Tuple[int, str, int], str, int, int]] = None
        for rel_path, start, last in sorted(members):
            tokens = file_tokens[rel_path]
            token_count = last - start + window
            occurrences.append(
                {
                    "end_line": tokens[last + window - 1][1],
                    "path": rel_path,
                    "start_line": tokens[start][1],
                    "token_count": token_count,
                }
            )
            rank = (-token_count, rel_path, start)
            if best is None or rank < best[0]:
                best = (rank, rel_path, start, last)
        assert best is not None
        normalized_key = "\x00".join(
            token
            for token, _line in file_tokens[best[1]][best[2]:best[3] + window]
        )
        results.append(
            candidate(
                "token_block_clone",
                normalized_key,
                occurrences,
                {
                    "member_count": len(occurrences),
                    "min_clone_tokens": window,
                    "normalization": (
                        "identifiers -> ID, string literals -> STR, numeric "
                        "literals -> NUM, punctuation kept verbatim, comments "
                        "stripped"
                    ),
                    "token_count": -best[0][0],
                },
            )
        )
    return results


def collect_evidence(
    roots: Sequence[Path],
    min_literal_length: int,
    min_text_block_chars: int,
    min_clone_tokens: int,
    exclude_globs: Sequence[str],
    excluded_path: Optional[Path] = None,
) -> Dict[str, Any]:
    resolved_roots = [root.resolve() for root in roots]
    multi_root = len(resolved_roots) > 1
    records: List[Tuple[Path, str, bytes, Optional[str]]] = []
    root_summaries: List[Dict[str, Any]] = []
    pruned_worktrees: List[str] = []
    skipped_symlinks: List[str] = []
    for root_index, root in enumerate(resolved_roots):
        prefix = str(root_index) + "/" if multi_root else ""
        files, pruned, symlinks = discover_files(root, excluded_path, exclude_globs)
        pruned_worktrees.extend(prefix + name for name in pruned)
        skipped_symlinks.extend(prefix + name for name in symlinks)
        artifact_count = 0
        for path in files:
            data = path.read_bytes()
            records.append(
                (path, prefix + relative_path(path, root), data, decode_text(data))
            )
            artifact_count += 1
        root_summaries.append(
            {
                "artifact_count": artifact_count,
                "index": root_index,
                "label": root.name,
            }
        )

    candidates: List[Dict[str, Any]] = []
    candidates.extend(collect_exact_file_candidates(records))
    candidates.extend(collect_literal_candidates(records, min_literal_length))
    candidates.extend(collect_font_family_candidates(records))
    candidates.extend(collect_text_block_candidates(records, min_text_block_chars))
    json_candidates, json_parse_errors = collect_json_shape_candidates(records)
    candidates.extend(json_candidates)
    candidates.extend(collect_token_clone_candidates(records, min_clone_tokens))
    candidates.sort(key=candidate_sort_key)

    counts = {kind: 0 for kind in KIND_ORDER}
    for item in candidates:
        counts[item["kind"]] += 1

    if multi_root:
        root_label = ",".join(
            str(summary["index"]) + "/" + summary["label"]
            for summary in root_summaries
        )
    else:
        root_label = root_summaries[0]["label"]

    return {
        "candidates": candidates,
        "notice": NOTICE,
        "scan": {
            "artifact_count": len(records),
            "ignored_directory_names": sorted(IGNORED_DIRECTORY_NAMES),
            "json_parse_errors": json_parse_errors,
            "min_clone_tokens": min_clone_tokens,
            "min_literal_length": min_literal_length,
            "min_text_block_chars": min_text_block_chars,
            "pruned_worktrees": sorted(pruned_worktrees),
            "requested_exclusions": {
                "items": sorted(set(exclude_globs)),
                "mode": "specified" if exclude_globs else "none",
            },
            "root": root_label,
            "roots": root_summaries,
            "scanner": scanner_identity(),
            "skipped_symlinks": sorted(skipped_symlinks),
            "text_artifact_count": sum(
                1 for record in records if record[3] is not None
            ),
        },
        "schema_version": SCHEMA_VERSION,
        "summary": {
            "candidate_count": len(candidates),
            "candidate_count_by_kind": counts,
        },
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Collect deterministic candidate evidence for possible abstractions. "
            "Emitted paths are always root-relative posix paths; with multiple "
            "roots each path is prefixed '<index>/' in argument order. "
            "Directories below a scan root that contain a .git entry (nested "
            "repositories, submodules, git worktrees) are pruned and disclosed "
            "in scan.pruned_worktrees. Symbolic links are never followed and "
            "are disclosed in scan.skipped_symlinks."
        )
    )
    parser.add_argument(
        "roots",
        nargs="+",
        help=(
            "One or more repository or artifact trees to scan. A single root "
            "behaves exactly as before; multiple roots are scanned as one "
            "corpus so cross-tree candidates can form."
        ),
    )
    parser.add_argument(
        "--output",
        help="Write JSON to this file instead of stdout. The output is excluded from its scan.",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        metavar="GLOB",
        help=(
            "Exclude files whose root-relative posix path matches this glob "
            "(fnmatch syntax, matched case-sensitively, before any multi-root "
            "index prefix). Repeatable. Echoed back in "
            "scan.requested_exclusions."
        ),
    )
    parser.add_argument(
        "--min-literal-length",
        type=int,
        default=16,
        help="Minimum normalized literal length (default: 16).",
    )
    parser.add_argument(
        "--min-text-block-chars",
        type=int,
        default=40,
        help="Minimum normalized document-block length (default: 40).",
    )
    parser.add_argument(
        "--min-clone-tokens",
        type=int,
        default=80,
        help=(
            "Window size in normalized tokens for the token_block_clone "
            "detector; also the minimum reportable clone length (default: 80)."
        ),
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    roots = [Path(root) for root in args.roots]
    for root in roots:
        if not root.is_dir():
            print("error: scan root is not a directory: " + str(root), file=sys.stderr)
            return 2
    if args.min_literal_length < 1 or args.min_text_block_chars < 1:
        print("error: minimum lengths must be positive integers", file=sys.stderr)
        return 2
    if args.min_clone_tokens < 2:
        print("error: --min-clone-tokens must be at least 2", file=sys.stderr)
        return 2

    output_path = Path(args.output).resolve() if args.output else None
    result = collect_evidence(
        roots,
        args.min_literal_length,
        args.min_text_block_chars,
        args.min_clone_tokens,
        args.exclude,
        excluded_path=output_path,
    )
    payload = stable_json_bytes(result)
    if output_path is None:
        sys.stdout.buffer.write(payload)
    else:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = output_path.with_name(output_path.name + ".tmp")
        temporary_path.write_bytes(payload)
        os.replace(str(temporary_path), str(output_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
