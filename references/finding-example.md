# Finding Skeleton and Worked Example

**Illustrative only. The paths below are placeholders (`/audit/root/...`); this document will not pass the shipped validator as-is, because the default `--require-existing-paths` mode and the whole-file sha256 check require real files. Substitute real absolute paths, real line numbers, and real hashes before validating. The authoritative field list is `evals/schemas/findings.schema.json`; the enforced semantics are in `validator-rules.md`.**

Recommended practice: author ONE finding, run `scripts/validate_findings.py` on the document (without `--canonical-out`), and fix it until it prints `valid: 1 finding(s)`. Only then author the rest. Vocabulary, precondition, and coupling errors caught on the first finding do not multiply by N findings. Write the canonical output exactly once, at the end, when the document is final; `--canonical-out` is an exclusive write.

## Skeleton

Every finding requires all 24 of these fields; `action` is the only optional one. Unknown keys are rejected at every level.

```json
{
  "id": "[stable id matching ^[A-Za-z0-9][A-Za-z0-9._:-]*$, unique in the document]",
  "artifact_class": "[one of: code, ui-component, design-token, font, asset, configuration, schema, prompt, workflow, test, dependency, documentation, mixed]",
  "claim_level": "[inventory | lexical-similarity | structural-similarity | semantic-overlap | behavioral-equivalence; never above the strongest evidence ceiling]",
  "claim": "[one bounded sentence; see the banned wording list in validator-rules.md]",
  "confidence": "[confirmed | probable | speculative]",
  "severity": "[critical | high | medium | low | info]",
  "locations": [
    { "path": "[absolute, normalized, existing, inside audit.root]",
      "start_line": 1, "end_line": 1,
      "sha256": "[optional: 64 lowercase hex digest of the WHOLE file, not the range]",
      "locator_kind": "[optional, only together with locator]", "locator": "[optional]" }
  ],
  "observations": [
    { "detail": "[raw detector fact, no interpretation]",
      "command": "[the exact command that produced it]",
      "sources": [ { "path": "[source object, same rules as locations]" } ] }
  ],
  "evidence": [
    { "id": "[E1-style, unique in the finding]",
      "type": "[one of the 25 canonical evidence types]",
      "detail": "[interpretive statement bounded by the type's ceiling]",
      "sources": [ { "path": "[source object]" } ],
      "metric": { "name": "[optional]", "value": 0 },
      "provenance": { "kind": "[deterministic-tool | direct-inspection | repository-history | runtime-observation | external-primary-source | human-confirmation]",
                      "producer": "[tool or person]", "method": "[how]" },
      "limitations": { "mode": "[none | specified]", "items": [] },
      "authority_rule": "[only on type authority-rule: {kind, authority_basis, rule}; see the compatibility matrix in validator-rules.md]" }
  ],
  "meaningful_differences": ["[every material difference; empty array only if none]"],
  "boundary_constraints": ["[constraints the proposal must respect]"],
  "squint": {
    "S": { "status": "[pass | fail | unknown]", "rationale": "[non-empty]", "evidence_refs": ["[required non-empty for pass and fail]"] },
    "Q": { "status": "...", "rationale": "...", "evidence_refs": [] },
    "U": { "status": "...", "rationale": "...", "evidence_refs": ["[for centralize/generate/parity: must cite the qualifying authority-rule evidence id HERE]"] },
    "I": { "status": "...", "rationale": "...", "evidence_refs": [] },
    "N": { "status": "...", "rationale": "...", "evidence_refs": [] },
    "T": { "status": "...", "rationale": "...", "evidence_refs": [] }
  },
  "disposition": "[reuse-existing | extract | centralize | generate | parity | link-and-monitor | keep | needs-evidence; check the precondition table in validator-rules.md BEFORE choosing]",
  "action": "[optional; must match the disposition per the mapping in validator-rules.md]",
  "recommendation": "[bounded, non-empty]",
  "maintenance_risk": { "level": "[critical | high | medium | low | unknown]", "rationale": "[non-empty]" },
  "change_risk": { "level": "...", "rationale": "..." },
  "affected_consumers": [],
  "owners": [],
  "public_boundaries": [],
  "verification_plan": {
    "steps": [
      { "command": "[exact executable command]", "prerequisites": [], "environment": "[non-empty]",
        "fixtures": [], "expected": "[non-empty]", "failure_means": "[what a failure disproves]" }
    ],
    "unrun_checks": ["[every relevant omitted check]"]
  },
  "rollback": { "boundary": "[non-empty]", "trigger": "[non-empty]", "steps": ["[at least one]"] },
  "missing_evidence": ["[required non-empty for needs-evidence; otherwise may be empty]"],
  "assumptions": [],
  "exclusions": []
}
```

Empty arrays are the correct value, not a gap, for `owners`, `public_boundaries`, `affected_consumers`, and `exclusions` in repositories without ownership metadata. Leave them empty rather than inventing entries.

## Worked example

A complete document (envelope plus one finding, including the step-4 triage ledger under `summary.triage`) that satisfies every validator rule except path existence. Verified: with `--allow-missing-paths` it validates cleanly; under the default mode it fails only with `path: does not exist` errors. The case is the modal one: two copies of one mechanism, disposition `extract`, claim level `semantic-overlap`.

```json
{
  "schema_version": "1.0",
  "audit": {
    "root": "/audit/root",
    "revision": "REPLACE-WITH-GIT-REVISION",
    "dirty_state": "clean",
    "date": "2026-08-07",
    "commands": [
      "git -C /audit/root rev-parse HEAD",
      "python3 scripts/collect_evidence.py --root /audit/root --out /audit/out"
    ]
  },
  "execution": {
    "output_directory": "/audit/out",
    "requested_exclusions": { "mode": "none", "items": [] },
    "scanner": {
      "version": "collect_evidence.py 1.0",
      "sha256": "0000000000000000000000000000000000000000000000000000000000000000",
      "options": ["--root", "/audit/root", "--out", "/audit/out"],
      "stderr": { "status": "empty", "content": "" }
    },
    "commands": [
      "python3 scripts/collect_evidence.py --root /audit/root --out /audit/out"
    ]
  },
  "limitations": {
    "mode": "specified",
    "items": ["Example document: paths are placeholders and hashes were not computed from real files."]
  },
  "scope": "Duplicate HTTP retry helpers under /audit/root/src.",
  "summary": {
    "triage": {
      "candidates_total": 3,
      "candidates_by_kind": { "token_block_clone": 2, "repeated_literal": 1 },
      "dropped_by_class": { "single-file": 1, "platform-vocabulary": 1 },
      "investigated": 1,
      "promoted": 1,
      "not_reached": 0
    }
  },
  "findings": [
    {
      "id": "EX-001",
      "artifact_class": "code",
      "claim_level": "semantic-overlap",
      "claim": "fetch_with_retry in src/a.py and load_with_retry in src/b.py implement the same documented retry policy over the same HTTP client boundary.",
      "confidence": "probable",
      "severity": "medium",
      "locations": [
        {
          "path": "/audit/root/src/a.py",
          "start_line": 40,
          "end_line": 72,
          "sha256": "0000000000000000000000000000000000000000000000000000000000000000",
          "locator_kind": "symbol",
          "locator": "fetch_with_retry"
        },
        {
          "path": "/audit/root/src/b.py",
          "start_line": 18,
          "end_line": 51
        }
      ],
      "observations": [
        {
          "detail": "Scanner reported normalized AST similarity 0.93 between src/a.py:40-72 and src/b.py:18-51 (scanner paths shown root-relative).",
          "command": "python3 scripts/collect_evidence.py --root /audit/root --out /audit/out",
          "sources": [
            { "path": "/audit/root/src/a.py", "start_line": 40, "end_line": 72 },
            { "path": "/audit/root/src/b.py", "start_line": 18, "end_line": 51 }
          ]
        }
      ],
      "evidence": [
        {
          "id": "E1",
          "type": "ast-structural-similarity",
          "detail": "Normalized AST similarity 0.93 across the two retry helpers: identical loop shape, backoff arithmetic, and caught exception set.",
          "sources": [
            { "path": "/audit/root/src/a.py", "start_line": 40, "end_line": 72 },
            { "path": "/audit/root/src/b.py", "start_line": 18, "end_line": 51 }
          ],
          "metric": { "name": "ast_similarity", "value": 0.93 },
          "provenance": {
            "kind": "deterministic-tool",
            "producer": "collect_evidence.py",
            "method": "normalized AST token comparison"
          },
          "limitations": { "mode": "specified", "items": ["Parser coverage limited to Python files."] }
        },
        {
          "id": "E2",
          "type": "boundary-analysis",
          "detail": "Both helpers sit behind the same module boundary: each is called only from src/api/client.py and neither is exported from the package.",
          "sources": [
            { "path": "/audit/root/src/api/client.py", "start_line": 10, "end_line": 30 }
          ],
          "provenance": {
            "kind": "direct-inspection",
            "producer": "auditor",
            "method": "read every call site and the package export list"
          },
          "limitations": { "mode": "none", "items": [] }
        }
      ],
      "meaningful_differences": [
        "load_with_retry logs retries at WARNING; fetch_with_retry logs at INFO."
      ],
      "boundary_constraints": [
        "Both callers live in the same package; no public API changes."
      ],
      "squint": {
        "S": {
          "status": "pass",
          "rationale": "Both helpers implement the documented retry policy for the same HTTP client responsibility.",
          "evidence_refs": ["E1", "E2"]
        },
        "Q": {
          "status": "pass",
          "rationale": "Identical inputs, outputs, exception contract, and timeout bounds at every call site.",
          "evidence_refs": ["E2"]
        },
        "U": {
          "status": "unknown",
          "rationale": "Repository history was not inspected and no authoritative derivation is claimed; not required for extract.",
          "evidence_refs": []
        },
        "I": {
          "status": "pass",
          "rationale": "The single material difference, the log level, is accidental drift and is preserved by a parameter in the proposal.",
          "evidence_refs": ["E1"]
        },
        "N": {
          "status": "pass",
          "rationale": "The proposed common form is one function with one optional log-level parameter, no wider.",
          "evidence_refs": ["E2"]
        },
        "T": {
          "status": "pass",
          "rationale": "Characterization tests cover both call sites and the change reverts in one commit.",
          "evidence_refs": ["E2"]
        }
      },
      "disposition": "extract",
      "action": "extract-local-abstraction",
      "recommendation": "Extract one retry helper into src/retry.py with a log-level parameter and route both call sites to it.",
      "maintenance_risk": {
        "level": "medium",
        "rationale": "The two copies have already diverged once on the caught exception set."
      },
      "change_risk": {
        "level": "low",
        "rationale": "Both call sites are internal to one package and covered by characterization tests."
      },
      "affected_consumers": [],
      "owners": [],
      "public_boundaries": [],
      "verification_plan": {
        "steps": [
          {
            "command": "python3 -m pytest tests/test_client.py -q",
            "prerequisites": ["pip install -e /audit/root"],
            "environment": "Python 3.11 virtualenv at /audit/root/.venv",
            "fixtures": ["tests/fixtures/http_replay.json"],
            "expected": "All characterization tests pass before and after the extraction.",
            "failure_means": "The shared helper does not preserve one call site's observed behavior."
          }
        ],
        "unrun_checks": [
          "No differential test over recorded production traffic was run."
        ]
      },
      "rollback": {
        "boundary": "The single extraction commit touching src/a.py, src/b.py, and src/retry.py.",
        "trigger": "Any characterization test failure or retry-count regression in staging.",
        "steps": [
          "git revert the extraction commit",
          "re-run python3 -m pytest tests/test_client.py -q"
        ]
      },
      "missing_evidence": [],
      "assumptions": ["Both call sites tolerate identical backoff timing."],
      "exclusions": ["Vendored copies under /audit/root/third_party were not compared."]
    }
  ]
}
```

## Why the example is shaped this way

- `claim_level: semantic-overlap` is licensed by E2 (`boundary-analysis`, ceiling `semantic-overlap`). E1 alone (`ast-structural-similarity`, ceiling `structural-similarity`) could not support it. The strongest declared evidence type sets the ceiling.
- The `claim` avoids every phrase in the banned behavioral-wording lexicon and states only the documented relationship the evidence shows.
- `disposition: extract` is an action recommendation, so E2 also satisfies the hard precondition that action dispositions carry `boundary-analysis` or `semantic-contract` evidence, and S, Q, I, N, T are all `pass` with cited evidence. U may stay `unknown` for `extract`; `centralize`, `generate`, and `parity` would additionally need a typed authority-rule evidence item cited in `squint.U.evidence_refs` and U not `fail`.
- `action: extract-local-abstraction` is the action mapped to `extract`. `parameterize-test` would also map to `extract` but costs `test-setup-overlap` evidence.
- The two locations differ in path, so the semantic-overlap comparison claim has two distinct locations. Two sources on the same path would need differing line bounds or locators to count as distinct.
- The `sha256` on the first location is the digest of the whole file, not of lines 40-72. Recompute it with `shasum -a 256 <file>` after any file change, or omit the field.
- `U.evidence_refs` is empty and valid because U is `unknown`; `pass` or `fail` on any gate requires at least one cited evidence id.
- `missing_evidence` is empty and valid because the disposition is not `needs-evidence`.
- `summary.triage` balances: `dropped_by_class` (2) plus `promoted` (1) plus `not_reached` (0) equals `candidates_total` (3), and `candidates_by_kind` also sums to 3. A `not_reached` above zero would additionally require a `limitations` item containing the phrase `not reached` and that count.
