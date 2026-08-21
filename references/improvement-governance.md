# Improvement governance

Scope: a completed audit needs only the "Audit learning receipt" section of this file. Everything else here governs candidate construction and promotion, and applies only when a skill change is actually being proposed.

The live skill is read-only during improvement work. A candidate is built in a separate, non-nested directory. Every change to the physical skill tree, including instructions and the evaluator manifest, produces a new `skill-sha256:` identity. `scripts/improvement.py` creates evidence and eligibility receipts only. It never copies a candidate over the live skill and never promotes a candidate.

## What the receipts prove

Content addressing detects later byte changes. It proves integrity, not authorship, authority, secrecy, or truthful execution. Fields such as `grader_owned`, `sealed`, `candidate_access_ended`, `grader_id`, and `approval_kind` are assertions when they appear in a local JSON file.

A promotion result is advisory unless both the approval and the holdout evidence are produced and authenticated by a trusted verifier outside the candidate's control. The verifier needs an operating-system boundary, a signature boundary, or an equivalent control that the candidate producer cannot access. Explicit approval must come from the person authorized to promote the skill.

## Evaluation boundaries

The package contains public regression fixtures only. `evals/governance-cases` is also public and is part of the frozen public evaluator identity. Nothing committed inside the skill is a sealed holdout.

A true holdout stays outside the live and candidate trees, is owned by the independent grader, and remains inaccessible to the candidate producer until candidate access has ended. Its result must bind the evaluated full-tree `subject_sha256`, target `eval_manifest_identity`, applicable immutable `model_intrinsic_key`, exact `input_corpus_hash`, and sha256 `external_suite_identity`. Model-independent runs use `[not-applicable]` only for `model_intrinsic_key`; the corpus hash remains required. Baseline and candidate runs must use the same external suite and corpus identities. A changed holdout requires a new comparison baseline and cannot rotate silently. A passed result must have zero failed tests, zero regressions, and an empty failures list.

The public result must come from `scripts/run_eval.py`. Its `identity.sha256` and full case set must exactly match `identity_sha256` and `public_case_ids` in the target skill's own `evals/manifest.json`. Its `subject.sha256` binds the exact whole skill tree evaluated. A selected public subset is useful for diagnosis but cannot support promotion.

## Model and scanner drift

Each run binds the target skill's own evaluator manifest, model policy, and scanner bytes. The scanner identity is the pair of declared version and file sha256. A change to either member is scanner drift.

A model-assisted run is conclusive only when every field named by `evals/model-policy.json` is present with the declared type. Hash fields must be lowercase sha256 values; temperature must be finite; seed must be an integer. Provider, model ID, immutable model revision, backend fingerprint, and reasoning effort must be stable identifiers. `[unknown]`, `[not-applicable]`, moving aliases such as `latest`, and a revision that merely repeats the model ID are rejected. Any changed comparison key requires a declared new-baseline reason. Model-independent checks record `[not-applicable]` for model-only fields.

## Audit learning receipt

Every completed, incomplete, failed, and zero-finding audit writes an immutable non-authorizing learning receipt. The receipt binds the exact skill tree, canonical findings, cited evidence, raw deterministic evidence, execution and scanner provenance, explicit limitations, outcome, and a bounded audit corpus identity. The corpus identity covers only validated cited repository paths plus revision, dirty state, scope, exclusions, and raw evidence. It does not recursively hash an arbitrary repository.

```sh
python3 /absolute/live/skill/scripts/improvement.py record-audit \
  --skill-root /absolute/live/skill \
  --findings /absolute/evidence/findings.canonical.json \
  --evidence /absolute/evidence/evidence.json \
  --outcome completed \
  --producer-id audit-producer-1 \
  --out-dir /absolute/outside-skill/audit-learning
```

Use `--outcome incomplete` or `--outcome failed` only with specified limitations. Attach `--failures` or `--dispositions` when those artifacts actually exist. The receipt always records `candidate_authority: false`. A zero-finding receipt with no failure or disposition trigger remains useful learning but cannot request a candidate.

## Candidate request

Start from an evaluation failure or an explicit user disposition. Findings alone cannot authorize self-improvement. A learning receipt may be supplied only when it carries one of those validated triggers.

Method, tool, and coverage gaps observed during a successful run are recorded as items in the findings document's top-level limitations and bound into the receipt's `limitations_hash`; they are not triggers. A gap report is model-authored prose about the model's own run and has no evidentiary value for its own claim. The auditor must surface such gaps to the user, and the user's explicit disposition, whose free-text rationale can carry the gap, is the only legal path from an observed gap to a candidate.

Adding a public evaluation case requires adding its intent to `CASE_INTENT` in `scripts/run_eval.py`; a case whose intent is missing or stale fails both `create-new-eval-identity` and the frozen-identity check. The command archives canonical, content-addressed copies of every input next to the request, rejects cited paths that do not exist under the audited root, and verifies that the live tree did not change.

```sh
python3 /absolute/live/skill/scripts/improvement.py propose \
  --skill-root /absolute/live/skill \
  --learning-receipt /absolute/evidence/audit-learning-<sha256>.json \
  --producer-id candidate-producer-1 \
  --out-dir /absolute/outside-skill/improvement-request
```

Build the candidate from that request in a separate directory. Do not edit the live tree. If a patch is attached, its receipt binds the exact patch bytes, but applying it is still a separate reviewed action.

## Immutable run receipts

Run the full public suite from each target tree. A separate trusted grader runs the external holdout. Both result artifacts attest that same target tree, evaluator identity, and applicable model and corpus identities. Then record each result against that target tree.

```sh
python3 /absolute/candidate/skill/scripts/improvement.py record-run \
  --skill-root /absolute/candidate/skill \
  --eval-manifest /absolute/candidate/skill/evals/manifest.json \
  --model-policy /absolute/candidate/skill/evals/model-policy.json \
  --scanner-version 1.2.0 \
  --result public=/absolute/evidence/public-result.json \
  --result holdout=/absolute/trusted-verifier/holdout-result.json \
  --producer-id candidate-producer-1 \
  --baseline-receipt /absolute/evidence/base-run-receipt.json \
  --model-independent \
  --out-dir /absolute/outside-skill/run-receipts
```

For a model-assisted run, supply `--model-record /absolute/evidence/model-record.json` instead of `--model-independent`. Supply the applicable `--model-change-reason`, `--scanner-change-reason`, or `--manifest-change-reason` whenever the corresponding baseline value changes. The command refuses silent drift.

Receipts are canonical JSON, named by their content hash, created with exclusive writes, and made read-only. Reusing the same name is accepted only when the bytes are identical.

## Explicit approval

The approver reviews the exact base and candidate receipt IDs, candidate skill identity and hash, evaluator manifest hash, model comparison key, model policy hash, public and holdout result hashes, both suite identities, grader identity, and all declared drift. The approval object uses every field required by `evals/schemas/approval-receipt.schema.json`.

To derive `approval_id`, remove `approval_id`, serialize the remaining object as compact UTF-8 JSON with sorted keys and one trailing newline, hash those bytes with sha256, and prefix the digest with `approval-sha256:`. Authentication remains external. A content-addressed self-assertion is not human approval.

## Promotion gate

The independent grader must be distinct from the candidate producer. Run the gate with the trusted live or baseline verifier, or with an external trusted verifier. Never use the candidate's copy of `improvement.py` to decide its own eligibility. Before starting any rerun subprocess, the local gate requires the candidate's complete `scripts/**` and `evals/governance-cases/**` inventories and file contents to match the trusted live baseline exactly. Missing, changed, extra, special, or linked entries fail closed, and candidate code is not executed. This includes import-shadow files such as `sitecustomize.py` or `json.py`.

When those executable surfaces match, the verifier reruns each copied subject twice with read-only files, a fixed minimal environment, a working directory outside the subject, Python `-I -S -B`, and a fixed `runpy` bootstrap that adds only the already verified script directory. Nested evaluator processes use the same controls. It checks byte-identical output, supplied candidate result bytes, target manifests, and declared file hashes. These controls reduce import and environment influence; they are not an operating-system sandbox and cannot safely contain arbitrary candidate code.

Any candidate change to executable evaluator code is therefore ineligible at the local gate. Review and adopt a new evaluator baseline only through an externally isolated and authenticated process controlled outside the candidate producer's boundary. A candidate may emit a run receipt, but the trusted gate revalidates that evidence.

The gate requires full deterministic public and external holdout passes, no failed or missing cases, no expected-output regressions, exact receipt bindings, unchanged holdout identity, model-record integrity, declared and approved drift, and an explicit approval bound to the whole comparison.

```sh
python3 /absolute/live/skill/scripts/improvement.py gate \
  --live-skill-root /absolute/live/skill \
  --candidate-skill-root /absolute/candidate/skill \
  --base-receipt /absolute/evidence/base-run-receipt.json \
  --candidate-receipt /absolute/evidence/candidate-run-receipt.json \
  --public-result /absolute/evidence/public-result.json \
  --holdout-result /absolute/trusted-verifier/holdout-result.json \
  --approval-receipt /absolute/trusted-verifier/approval-receipt.json \
  --grader-id independent-grader-1 \
  --out-dir /absolute/outside-skill/promotion-gate
```

Exit zero means the supplied evidence is eligible under these checks. It does not mutate either tree and does not prove that caller-supplied identities are authentic. Promotion remains a separate action by the authorized person after verifying the external trust boundary.
