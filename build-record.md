# Build record: Abstraction Police

## Identity

- Version: 1.2.1
- Built: 2026-08-06; revised 2026-08-07 and 2026-08-21
- Purpose: find latent reuse opportunities across code and non-code artifacts while rejecting abstractions that share appearance but not responsibility, contract, authority, or change pressure.
- Public evaluator identity at 1.0.0 freeze: `eb42a9f0b90e3ec2936b68dd4ae2586f6e46e9433924f4b01e71ea300abaca07`
- Public evaluator identity at 1.1.0 freeze: `69630678a0414c8494812d0864abac0e974b6fed3f27a54b7de0b52e50dd8641`
- Public evaluator identity at 1.2.0 freeze: `9af3d533542f460bd5ddbd269e0b0616c228c8d2bcfe53cda85dd0c425634c4e` (local only; the 1.2.0 tag cannot be evaluated from a clone, see revision 1.2.1)
- Public evaluator identity at 1.2.1 freeze: `c17b6c0af4c57bfde701af924199c5945e0989e14d0b2c068abea34ef0fc86d7`

## Research basis

The method was derived from primary papers and normative specifications covering information hiding and program families, behavioral contracts, clone genealogy and intentional cloning, anti-unification and schema matching, logical change coupling, behavior-preserving refactoring, differential and property testing, design tokens, workflow semantics, prompt variability, perceptual asset comparison, font metadata, evaluation design, reusable holdouts, and provenance. The full annotated source list is in `references/primary-sources.md`.

The resulting decision rule separates four layers:

1. Representation discovers candidates.
2. Contract bounds what can safely be shared.
3. Role establishes responsibility and reason to change.
4. Derivation identifies authority, generation, mirroring, vending, and caching.

## What was built

- A broad artifact taxonomy spanning code, queries, UI, tokens, fonts, media, configuration, policy, infrastructure, schemas, models, workflows, prompts, tests, fixtures, documentation, dependencies, and cross-format families.
- Deterministic discovery for exact files and assets, repeated normalized literals, font-family values, normalized document blocks, and recursive JSON shapes.
- Evidence ceilings that prevent lexical or structural similarity from becoming an unsupported behavioral claim.
- The six-gate SQUINT adjudication protocol and eight mutually exclusive dispositions.
- A strict findings schema and validator with absolute existing-path checks, file hashes, line bounds, typed evidence provenance and limitations, authority rules, verification plans, and rollback boundaries.
- A frozen exact-output public evaluator with positive, anti-abstraction, and governance cases.
- Whole-tree subject attestation so a passing result cannot be replayed against different skill instructions or scripts.
- Model comparison records that fail closed when immutable revision, backend fingerprint, configuration, tool, prompt, corpus, skill, or evaluator identity is missing or changed.
- External holdout and approval bindings, trusted-code public reruns, independent-grader separation, and content-addressed advisory promotion receipts. A local rerun is permitted only when the candidate's complete executable evaluator surface exactly matches the trusted live baseline; evaluator-code changes require external isolation and manual baseline adoption.
- A mandatory `record-audit` step that writes immutable learning evidence after completed, incomplete, failed, and zero-finding runs without granting self-improvement authority.

## Measured improvement during construction

An independent forward audit correctly separated eight synthetic lookalikes across design tokens, platform validators, policy documentation, workflows, prompts, font assets, semantic color aliases, and domain-specific identifiers. The grader found one minor error: maintenance ownership was treated as source-of-truth authority for token generation. The final rubric, schema, validator, and governance regression now require a typed, cited authority rule for `centralize`, `generate`, and `parity`; ownership alone is explicitly insufficient.

An adversarial review then reproduced result replay, moving-model-alias acceptance, findings-schema contradictions, unsupported unified-change claims, inconsistent passed-holdout failures, fabricated improvement evidence paths, and unsafe execution of candidate-owned evaluator code. Each reproduced case was converted into a deterministic regression before the evaluator identity was frozen. The final rerun gate rejects altered runners and import-shadow files before process launch and verifies that their attempted outside marker remains absent.

## Verification at freeze

- Public cases: `anti_abstraction`, `governance`, `shared_candidates`
- Governance regressions: 12 passed
- Frozen evaluator inputs: 44
- Two full public runs: byte-identical stdout and empty stderr
- Scanner outputs: exact golden matches
- Python: Python 3.9 parsing and compilation passed
- JSON: all package JSON parsed
- Skill package: skill-creator quick validation passed

## Limits

- Similarity detection remains candidate generation. Semantic adjudication still requires repository evidence and can abstain.
- Model sampling cannot be made perfectly deterministic by this package. Model-assisted evaluation is inconclusive when immutable runtime metadata is unavailable and never overrides deterministic checks.
- Local content hashes prove byte integrity, not human identity, authorization, holdout secrecy, or truthful execution. Approval and holdout authenticity require a trust boundary outside the candidate producer.
- The public suite is intentionally visible. A real holdout must remain external to this directory and must bind the exact evaluated subject, evaluator, model record, and input corpus.

## Revision 1.1.0 (2026-08-07)

### Trigger and authorization

The first field audit (a production iOS app, 2026-08-06/07) was followed by a meta-audit of this skill: two orchestrated workflows produced 70 improvement proposals across seven lenses, 49 of which received adversarial verdicts (CONFIRMED/REVISED/REJECTED). Pierson Davis gave the explicit user disposition to implement the findings on 2026-08-07. That disposition is the improvement trigger required by references/improvement-governance.md; this revision was applied directly to the live tree on the owner's instruction, and the owner's review of the diff constitutes the external baseline adoption that the local promotion gate cannot perform for evaluator-code changes. The evaluator identity was deliberately re-frozen via create-new-eval-identity after all changes landed.

### What changed

- SKILL.md: pre-flight scoping and top-level partition proof in step 1; scanner exclusions via --exclude in step 2; re-runnable command rule and detector-recipes pointer in step 3; triage ledger with coverage-based stopping rule, cross-artifact sweep, and provisional group boundary in step 4; claim-wording binding in step 5; re-cut rule in step 7; harvest-repo-checks in step 8; validate-early / re-derive / emit-once protocol in step 9; report structure in step 10; dual-run guidance and validation-as-formation-constraint in the operating boundary.
- references/adjudication-rubric.md: claim-wording ladder with per-rung licensed vocabulary; prose-report ceiling binding; coextensivity rule for SQUINT gates; disposition-partition rule; per-member locatability; verbatim-command and count-provenance rules; single-source-of-truth declaration for the vocabulary.
- New references: validator-rules.md (approximately 75 enforced rule sites, all cited against the current validator), finding-example.md (24-field skeleton plus a machine-verified worked example), detector-recipes.md (14 verified recipes, one per canonical evidence type, with git-cochange fanout guard, anti-upgrade rule, harvest section, and evidence-integrity preconditions).
- references/improvement-governance.md: scope header; routing paragraph for method/tool/coverage gaps observed in successful runs; case-intent maintenance note.
- scripts/collect_evidence.py (1.1.0): worktree/nested-checkout pruning with disclosure; multiple roots and repeatable --exclude; Type-2 token-block clone detector (token_block_clone, lexical-similarity ceiling, default 80-token window); repeated_literal shape classification, comment-only and truncation flags, distinct-file counts; salience ordering; json_key_shape subsumption and basename-uniformity labels; mapping-key fix recovering ternary and case literals; scanner self-identity in output.
- scripts/validate_findings.py: EXACT_IDENTITY_WORDING rule (byte-identity vocabulary requires exact-hash evidence); duplicate evidence_refs rejected; opt-in execution.scan_roots partition coverage check; finding-id prefixes on error messages; all sixteen controlled vocabularies single-sourced from the schema with fail-closed errors.
- scripts/run_eval.py: case-intent entries for the two new cases; create-new-eval-identity refuses missing or stale case intents; frozen-identity check verifies case_intent matches public case ids.
- evals: new discovery cases duplicate_subtree (worktree pruning must suppress cross-tree copies while the primary tree scans) and token_block_clones (Type-2 clones surface, sub-threshold overlap stays silent); all four discovery goldens regenerated for scanner 1.1.0 output; findings.schema.json gains optional execution.scan_roots and drops the unread x-similarity-only-evidence key; rubric.json gains a source_of_truth header.
- agents/openai.yaml: default prompt aligned with the read-only operating boundary.

### Recorded rejections (do not re-propose without new evidence)

- Python-only AST detector: privileges one language in a scanner for arbitrary trees (SCAN-07, verdict-confirmed).
- Extending BEHAVIOR_WORDING to nominal forms: measured false positives on bounded disclaimers in a real findings document.
- Validator metric-echo check and recursive partition coverage: measured infeasible or zero-information.
- disposition_scope structured field: inert by construction; prose coextensivity plus a second reader is the permanent control (AP-SPLIT-5 verdict).
- Mixed-disposition eval fixture: discovery cases exercise the scanner only and cannot regression-test adjudication rules (AP-SPLIT-6 verdict).
- json_key_shape suppression: refuted by execution on both fixtures; shipped as subsumption labels instead.
- .claude ignore entry: worktree pruning already handles nested checkouts; a name-based ignore would blind the scanner to agent-config duplication.
- Independent dual audits as the default remedy: measured to reproduce load-bearing digests while sharing method blind spots; targeted re-derivation plus partition proof buys more per token.

### Known deferrals

- E6: improvement.py accepts any hand-written failures artifact as an evaluation-failure trigger; binding it to the evaluation-result schema touches improvement.py plus the governance fixture and golden, and is sequenced for a separate externally-reviewed change.
- E3: no eval case yet exercises the noise regime of a real repository (hundreds of candidates); the triage protocol addresses the operator side, detector-scale coverage remains open.
- x-similarity-only-evidence was removed rather than kept with a derivation note (the E7 verdict preferred keeping it); validator-rules.md now carries the reader-facing vocabulary and the single-source declaration makes a dead derived copy contradictory. Recorded here because it diverges from the verdict.

### Verification at re-freeze

- Public cases: anti_abstraction, duplicate_subtree, governance, shared_candidates, token_block_clones (5 cases, 54 frozen evaluator inputs).
- create-new-eval-identity preflight: 5/5 passed.
- Governance case: 12 regressions passed, stdout byte-identical to golden, before and after validator changes.
- Real-document regression: the 2026-08-06 field-audit findings document validates with exactly one new error, the measured AP-002 byte-identity true positive.
- Full public suite: two runs recorded below; byte-identical stdout required.

## Revision 1.2.0 (2026-08-21)

### Trigger and authorization

A read-only adversarial audit of this skill by an external model (run through OpenRouter's stealth model "Ox Alpha" on 2026-08-21), followed by an independent re-verification of every cited line and a re-check of the determinism surface. Pierson Davis gave the explicit user disposition to apply the resulting changes and publish the skill on 2026-08-21. As with 1.1.0, the revision was applied to a candidate copy on the owner's instruction, the owner's review of the diff constitutes the external baseline adoption that the local promotion gate cannot perform for evaluator-code changes, and the evaluator identity was re-frozen via create-new-eval-identity after all changes landed.

### What changed

- scripts/validate_findings.py: `summary` is required and `summary.triage` is validated: exact key set; non-negative integer counts with booleans rejected; `candidates_by_kind` sums to `candidates_total`; `dropped_by_class + promoted + not_reached == candidates_total`; `promoted <= investigated`; `investigated + not_reached <= candidates_total`; and when `not_reached > 0`, a `limitations` item (mode `specified`) containing the phrase `not reached` and that count. The helper `_validate_summary` is appended after `main()` so every earlier line citation in validator-rules.md stays valid; the call site occupies the same two lines the old object check used.
- evals/schemas/findings.schema.json: `summary` added to the top-level `required` list; `$defs.summary` and `$defs.triage_ledger` added.
- scripts/collect_evidence.py (scanner 1.2.0, output schema 1.2): symbolic links to files or directories are never followed and are disclosed in `scan.skipped_symlinks`; previously they were skipped silently, which contradicted the skill's own rule that a scan boundary is never implicit. Module docstring and CLI description state the rule.
- evals/governance-cases/test_governance.py: fixture documents carry a triage ledger; two regressions added, `triage-ledger-is-enforced` (balanced ledger accepted; missing summary, unbalanced sums, and an unnamed not-reached count rejected; a named not-reached count accepted) and `scanner-discloses-skipped-symlinks`; the model-record fixture uses neutral provider and model identifiers.
- evals/expected: the four discovery goldens regenerated for the `skipped_symlinks` key and the new scanner identity; the governance golden regenerated for the two new checks.
- SKILL.md step 2 (symlink disclosure) and step 4 (enforced ledger arithmetic); references/validator-rules.md (six new rows, schema-enforcement note, appendix convention); references/finding-example.md (worked example carries `summary.triage`; re-verified with --allow-missing-paths); references/adjudication-rubric.md (metric rule states that the validator checks shape only and step 9 re-derivation verifies values); references/improvement-governance.md (scanner version in the example command).
- Public packaging: README.md, LICENSE (MIT), CONTRIBUTING.md, .gitignore, .gitattributes (LF normalization so any checkout reproduces the identity), and .github/workflows/eval.yml (the suite twice on Linux and macOS, Python 3.9 and 3.12, every result byte-identical across all jobs).

### Recorded rejections (do not re-propose without new evidence)

- Validator metric-echo check: re-raised by the external audit, still rejected (measured false-positive-prone during 1.1.0); the rubric now says explicitly that the validator checks a metric's shape and step 9 verifies its value.
- Recording the Python Unicode database version in scanner output: it would make the public result differ across Python versions for no functional reason. The NFKC and casefold dependency is documented in README instead and CI runs the suite on two Python versions.

### Verification at re-freeze

- Public cases: 5; frozen evaluator inputs: 54; governance regressions: 14.
- create-new-eval-identity preflight: 5/5 passed.
- Full suite: two byte-identical runs on Python 3.9.6 (Unicode database 13.0.0); the full result bytes, including identity and case statuses, were identical on Python 3.11 (Unicode 14.0.0) and Python 3.12 (Unicode 15.0.0); CI repeats the suite on Linux and macOS and compares every result file.
- references/finding-example.md worked example: validates with --allow-missing-paths (`valid: 1 finding(s)`).

## Revision 1.2.1 (2026-08-22)

### Trigger and authorization

Publication defect found by verifying a fresh clone of the pushed 1.2.0 tag, and independently by the first CI run, which failed on both jobs. Pierson Davis authorized the publication and this fix on 2026-08-22.

The defect: the `duplicate_subtree` fixture's nested-checkout marker was a file literally named `.git`. Git refuses to add a path whose component is `.git`, so `git add -A` dropped it without an error anyone read, the 1.2.0 commit shipped 70 of the 71 tree files, and every clone failed `verify_frozen_identity` with `missing_file`. The local tree passed because the file was present locally. Two controls that should have caught it did not: the identity manifest froze a path that cannot be committed, and the subject attestation skipped that same path, because `tree_identity` treats any path component named `.git` as an ignored directory. The suite was never run from a clone before publishing. That gap is the finding, not the fixture.

### What changed

- evals/cases/duplicate_subtree/.worktrees/copy1: the marker is stored as `dot-git` and is now a normal, committable file.
- scripts/run_eval.py: `materialize_case` copies each discovery case to a temporary directory and renames `dot-git` to `.git` before the scanner runs. The scanner emits only root-relative paths and the root's basename, so output is unchanged; all four discovery goldens are byte-identical to their 1.2.0 bytes. A side effect strengthens the suite: the two runs of a case now use different absolute paths, so the byte-identity check would catch an absolute path leaking into scanner output, which it could not when both runs shared one path.
- scripts/run_eval.py: `required_input_differences` fails closed with `path_not_representable_in_git` for any identity-bearing path containing a `.git` component, so a manifest that cannot survive a clone can no longer be frozen.
- Subject attestation now covers 71 files rather than 70: with the marker renamed, `tree_identity` no longer skips it.
- CONTRIBUTING.md documents the marker convention; README drops the jargon verb "DRY".

### Verification at re-freeze

- Public cases: 5; frozen evaluator inputs: 54; governance regressions: 14; subject files: 71.
- Discovery goldens: byte-identical to 1.2.0 (the fix changes staging, not output).
- duplicate_subtree still prunes `.worktrees/copy1`, scans 2 primary-tree artifacts, and reports no candidate from a pruned path.
- Two byte-identical runs on Python 3.9.6; full result bytes identical on Python 3.11 and 3.12.
- Verified from a fresh `git clone` of the public repository, not only from the working tree. That check is now the release gate.
