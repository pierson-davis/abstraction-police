# Adjudication Rubric

Apply this rubric to each candidate group. Preserve raw observations separately from interpretation.

## Contents

- [Evidence and claim ceilings](#evidence-and-claim-ceilings)
- [Claim wording](#claim-wording)
- [SQUINT gate](#squint-gate)
- [Gate interpretation](#gate-interpretation)
- [Dispositions](#dispositions)
- [Risk and priority](#risk-and-priority)
- [Required finding record](#required-finding-record)
- [Verification-plan requirements](#verification-plan-requirements)

## Evidence and claim ceilings

Never make a stronger claim than the strongest applicable evidence permits.

The canonical vocabulary (evidence types, claim levels, ceilings, dispositions, artifact classes) is defined once, in `evals/schemas/findings.schema.json`. This table and `evals/rubric.json` are readable restatements of that source of truth; when they disagree, the schema wins and the restatement is the defect.

| Canonical evidence type | Maximum claim level | Permitted statement and boundary |
|---|---|---|
| `inventory` | `inventory` | State that the cited artifacts and metadata were observed |
| `exact-content-hash`, `normalized-text-similarity`, `token-similarity`, `literal-overlap`, `asset-exact-hash`, `asset-perceptual-similarity` | `lexical-similarity` | State exact or normalized representational similarity; do not infer shared meaning or behavior |
| `ast-structural-similarity`, `control-flow-similarity`, `schema-shape-overlap`, `prompt-contract-overlap`, `config-key-overlap`, `workflow-step-overlap`, `test-setup-overlap`, `dependency-capability-overlap` | `structural-similarity` | State similarity in the named parsed structure; do not infer runtime equivalence or common ownership |
| `existing-abstraction`, `git-cochange`, `call-graph`, `boundary-analysis`, `semantic-contract`, `human-confirmation` | `semantic-overlap` | State the documented relationship, boundary, contract, historical association, or dated human intent; do not infer untested behavior or future causal coupling |
| `authority-rule` | `semantic-overlap` | State only the cited authoritative derivation, explicit parity invariant, or shared normative requirement; ownership or maintenance preference alone is not authority |
| `differential-test`, `contract-test`, `runtime-trace` | `behavioral-equivalence` | State bounded equivalence only for the named inputs, environment, version, trace, and tolerance; do not claim universal equivalence |
| Model interpretation | No evidentiary value | State a hypothesis and identify evidence needed; do not cite the model as evidence or let it grade its own hypothesis |

Use these claim levels in increasing order: `inventory`, `lexical-similarity`, `structural-similarity`, `semantic-overlap`, `behavioral-equivalence`. Select a level no higher than the strongest cited canonical evidence type. Downgrade the claim whenever provenance, parser coverage, environment, or test-domain limitations require it. Require at least one bounded `differential-test`, `contract-test`, or `runtime-trace` before selecting `behavioral-equivalence`; never let `human-confirmation` raise a claim above `semantic-overlap`, and never encode model interpretation as evidence.

## Claim wording

The claim sentence carries the same ceiling as `claim_level`. A sentence may state facts at several rungs, but every rung a word asserts needs its own cited evidence in that finding. Words, not just the enum, are adjudicated.

| Rung asserted | Licensed vocabulary | Cited evidence required for that word |
|---|---|---|
| inventory | occurs in, present at, declared in, appears N times, N copies exist | any |
| lexical, normalized | near-identical, differ only in whitespace, differ on N of M lines, same text after normalization, N% token overlap, shares the literal X | `normalized-text-similarity`, `token-similarity`, `literal-overlap`, `asset-perceptual-similarity` |
| lexical, exact | byte-identical, bit-identical, byte-for-byte, character-for-character, textually identical, identical bytes, the same bytes, verbatim, exact copy, exact duplicate | `exact-content-hash` or `asset-exact-hash` only. No other evidence type licenses these words. |
| structural | AST-identical, structurally identical, same control flow, same branch ordering, same key set, same shape, identical signature | `ast-structural-similarity`, `control-flow-similarity`, `schema-shape-overlap`, `config-key-overlap`, `prompt-contract-overlap`, `workflow-step-overlap`, `test-setup-overlap`, `dependency-capability-overlap` |
| semantic | represents one concept, declared source of truth, documented as mirroring, counterpart of, same declared responsibility, co-changed N times | `existing-abstraction`, `semantic-contract`, `boundary-analysis`, `call-graph`, `git-cochange`, `authority-rule`, `human-confirmation` |
| behavioral | behaviorally equivalent, same behavior, identical behavior, semantically identical, semantically equivalent, interchangeable, functionally equivalent, drop-in replacement, produces the same output, safe to swap | `differential-test`, `contract-test`, or `runtime-trace`, and only for the named inputs, environment, version, and tolerance |

Bare `identical` takes the rung of the noun it modifies: `identical bytes` is exact, `identical key set` is structural, `identical behavior` is behavioral. Always attach the noun. An unqualified "the two are identical" reads as the exact rung and needs a content hash.

Forbidden at every rung without evidence that covers the whole domain: always, guaranteed, in all cases, cannot diverge, will never differ. No bounded test licenses a universal quantifier. State the bound instead.

Not rung-bound, and never a violation on their own: copy, copies, duplicate, duplication, mirror, sibling, parallel, the same helper, the same concept. These name a relationship rather than a measured identity. Use them freely; do not treat them as evidence.

The validator enforces the behavioral row mechanically: `behaviorally equivalent`, `same behavior`, `identical behavior`, `semantically identical`, `semantically equivalent`, and `interchangeable` in a `claim` require `claim_level: behavioral-equivalence`, which in turn requires differential-test, contract-test, or runtime-trace evidence. It also enforces the exact-lexical row: byte-identity vocabulary requires cited `exact-content-hash` or `asset-exact-hash` evidence. Validation fails otherwise. Every wording pattern enforced by `scripts/**` must be listed verbatim in this rubric; a rule the author cannot read before writing is a trap, not a control. See references/validator-rules.md for the complete enforced-rule catalog.

Claim ceilings bind the prose report as well as the findings document. Never state or paraphrase a finding in the report at a higher claim level than its recorded `claim_level`, and never describe a similarity result as equivalence.

## SQUINT gate

Record `pass`, `fail`, or `unknown` for every gate. Cite exact evidence for each result. Each gate result is coextensive with the locations the finding cites: it must hold for all of them and range over none beyond them. A rationale that holds for only some cited locations means the candidate group spans more than one disposition. A rationale, claim, or recommendation that names an artifact no location cites means the finding is under-cited. State the gate about the whole finding and nothing else, or re-cut the finding until you can.

### S: Shared responsibility

Require evidence that the artifacts implement, express, or derive from the same domain concept, policy, asset, or mechanism. Fail when resemblance crosses unrelated responsibilities. Mark unknown when the repository does not establish intent or authority.

### Q: Qualified contract compatibility

Compare inputs, outputs, types, invariants, errors, side effects, permissions, accessibility, timing, ordering, compatibility, and nonfunctional constraints that matter for the artifact type. Pass only when one bounded contract can preserve required behavior. Treat security, licensing, data-authority, or irreversible migration conflicts as hard failures.

### U: Unified change pressure

Look for the same reason to change through shared requirements, policy, source authority, consumers, defect propagation, or repeated co-change. Use history as evidence for the inspected period, not as proof of future intent. Ownership and maintenance convenience are weak context, not authority. Pass without history only when a cited authoritative derivation, shared normative requirement, or contractual invariant explicitly requires the relationship.

### I: Intentional variation understood

Enumerate every material difference and classify it as required variability, accidental drift, derivation output, or unresolved. Pass only when the proposal preserves required differences and explains accidental ones. Mark unknown rather than inventing a rationale.

### N: Narrow generalization

Propose the least-general common form. Prefer a small primitive plus semantic wrappers over a broad framework. Fail when the abstraction needs unrelated flags, weakly typed option bags, caller knowledge of internals, excessive indirection, or an interface larger than the stable shared core.

### T: Testable transition

Require a concrete way to compare the current and proposed states and a bounded rollback. Name exact commands, fixtures, environments, consumers, expected invariants, and failure conditions. Mark unknown when required behavior cannot be observed. Fail when the transition cannot be made safely within the authorized scope.

## Gate interpretation

- Require `S`, `Q`, `I`, `N`, and `T` to pass before recommending a structural consolidation. Treat `U` as material evidence, but do not require repository history when the other gates establish a safe local extraction or reuse.
- Require a typed, cited `authority-rule` before recommending `centralize`, `generate`, or `parity`. A `U` pass, ownership, or maintenance pressure without that rule is insufficient.
- For `centralize`, accept a declared source of truth or shared normative requirement. For `generate`, require an authoritative derivation source or executable generation rule. For `parity`, require an explicit parity or contractual invariant.
- Require a passed `S`, a documented shared invariant, and a passed `T` before recommending `parity` when direct consolidation fails.
- Assign `needs-evidence` when a required gate remains unknown.
- Assign `keep` when a hard gate fails and no useful relationship must be enforced.
- Consider `link-and-monitor` or `parity` when shared concern exists but separation remains necessary.
- Do not collapse gate results into an uncalibrated composite score. Report evidence strength and risk separately.

## Dispositions

Assign exactly one primary disposition.

A finding is defined by its disposition, not by its detected similarity. A detector groups by representation; adjudication cuts by contract, role, and derivation. When those cuts disagree, the finding boundary follows adjudication: partition the candidate group into disposition-equivalence classes and emit one finding per class. Never carry a member under a disposition its own evidence does not support, in either direction.

The partition is bounded by the eight dispositions, not by group size: members sharing a disposition and the same missing evidence stay in one finding, so a large group yields two or three findings, never one per member. A member whose only difference raises a question outside this vocabulary, such as whether an artifact is dead, is not a separate disposition; record it under `observations` or `missing_evidence`. Give each resulting finding the full required record and name the sibling identifiers in `assumptions` so the original group stays reconstructable. Splitting needs no schema change: identifiers must be unique and two findings may cite overlapping locations. Before splitting, check that each resulting finding still cites at least two distinct locations; a class reduced to a single location can only carry an `inventory` claim.

### `reuse-existing`

Route callers or consumers to an existing canonical artifact that already satisfies the full contract. Do not create a new abstraction. Verify every migrated consumer and remove obsolete material only under explicit remediation authority.

### `extract`

Create the smallest shared primitive, helper, component, token, subworkflow, or prompt module. Preserve semantic wrappers where names, policies, or public contracts differ. Reject extraction when parameterized holes dominate the shared core.

### `centralize`

Designate one source of truth and make consumers reference it directly. Use for authoritative policy, configuration, schema, token, asset, or exact text when consumer environments support direct reuse.

### `generate`

Designate one authoritative source and derive required variants deterministically. Use when consumers require separate formats, languages, build outputs, resolutions, or checked-in artifacts. Include freshness and reproducibility checks.

### `parity`

Keep implementations separate and enforce a shared invariant with deterministic comparison, contract tests, differential tests, or synchronization checks. Use when platform, release, permission, or failure-isolation boundaries make direct reuse unsafe.

### `link-and-monitor`

Keep artifacts separate but record their relationship, authority, owners, divergence policy, monitored signal, and response. Use for semantic counterparts that should be discoverable but need neither strict equality nor automatic synchronization.

### `keep`

Preserve intentional duplication without enforcement. Record the concrete reason, such as locality, independent oracle value, experimentation, trusted isolation, low change cost, licensing, or incompatible contracts. Add a revisit trigger when one is known.

### `needs-evidence`

Defer adjudication. Name the missing evidence, exact acquisition step, responsible boundary when known, and the decision that evidence would unlock. Do not disguise uncertainty as a low-confidence consolidation recommendation.

## Risk and priority

Raise priority when independent copies repeatedly receive the same fixes, inconsistent copies caused defects, a security or policy invariant can drift, or many consumers amplify manual change. Lower priority when copies are stable, cheap, intentionally isolated, or scheduled for deletion.

Raise change risk for public interfaces, migrations, permissions, secrets, concurrency, transactions, generated or vendored outputs, independent release trains, weak test coverage, nondeterministic behavior, or many external consumers.

Recommend action from the combination of maintenance risk, change risk, and evidence strength. Do not use duplication volume alone.

## Required finding record

Include all of the following:

- Record `audit.root`, `audit.revision`, `audit.dirty_state`, absolute `audit.date`, and every audit command once for the document. Record `scope` separately. Record top-level `execution` with the absolute output directory, explicit requested exclusions, scanner version and hash, exact options, stderr status and content, and commands.
- Every count stated anywhere in the document, in `scope`, `limitations`, `execution`, a `claim`, an `observation.detail`, or a `metric`, must come from an unbounded counting command (`| wc -l`), a complete listing, or a scanner-emitted count such as `scan.artifact_count` or `summary.candidate_count`. Record the producing command in `audit.commands` for a document-level count and in the owning `observation.command` for a finding-level count. A number read off truncated, paged, `head`/`tail`-bounded, or otherwise display-limited output is not an observation; state it as unknown or omit it. When a count appears in a `claim`, carry it as a `metric` on the evidence item that produced it so a re-derivation pass has something to check. The validator checks only a metric's shape; the step 9 re-derivation is what verifies its value.
- Represent top-level and per-evidence limitations explicitly with `mode` and `items`; use `mode: none` only with an empty list and `mode: specified` only with concrete items.
- Assign each finding a stable `id` and canonical `artifact_class`.
- Populate `locations` with every normalized absolute path. Add line bounds or `locator_kind` and `locator` where the file alone is not precise. Apply the narrowest stable locator required by the SKILL procedure to each group member individually: when the finding is about a symbol, cite that symbol's own bounds, not the bounds of the enclosing artifact containing it. A member a reader cannot navigate to directly from `locations` is not cited. A location recording the absence of a member is not a member: move it to `observations`, which requires its own detail, command, and sources. After any such move, confirm the finding still cites at least two distinct locations if its claim level is above `inventory`.
- Preserve raw detector facts and exact commands under `observations`. Retain any scanner root-relative path in the observation detail while citing the resolved absolute sources.
- `observation.command` is the exact command that produced `observation.detail`, re-runnable verbatim from `audit.root` on a machine with the same tools. It is not a description of what you did. Reject placeholder tokens (`<out>`, `<path>`, `(...)`, `/absolute/path/to/...`) and substitute the resolved absolute path you actually used. Reject prose paraphrases inside `python3 -c`: write any ad-hoc analysis to a file under `execution.output_directory` and cite that script. Check that flags match the syntax used; `|` alternation needs `grep -E`, and a `grep` that returns nothing cannot have produced a detail listing matches. Before finalizing, re-run every command you recorded; a command whose output no longer supports its detail is not evidence.
- Assign each evidence item a unique `E1`-style identifier. Record its canonical evidence `type`, detail, sources, metric when available, typed provenance, and explicit limitations. A typed `authority-rule` must cite the rule-bearing source and name its authority basis.
- Select `claim_level`, write one bounded `claim` sentence, and record `confidence` and `severity` independently.
- Enumerate `meaningful_differences` and `boundary_constraints` without interpreting a missing value as equivalence.
- Populate all six `squint` gates with `pass`, `fail`, or `unknown`, a rationale, and applicable evidence identifiers.
- Assign one primary `disposition`. Add the optional `action` only when the canonical action vocabulary improves implementation clarity.
- Write a bounded `recommendation`, then record `maintenance_risk` and `change_risk` with separate levels and rationales.
- List `affected_consumers`, `owners`, and `public_boundaries`; leave arrays empty rather than inventing entries.
- Populate `verification_plan.steps` with exact commands, prerequisites, environment, fixtures, expected result, and failure meaning. List every relevant omitted check under `unrun_checks`.
- Populate `rollback` with a bounded target, trigger, and recoverable steps.
- List `missing_evidence`, `assumptions`, and `exclusions` explicitly. `needs-evidence` requires at least one nonempty `missing_evidence` item.
- Cite only paths that exist under the declared audited root when recording or proposing from findings.

## Verification-plan requirements

Name executable commands rather than writing “run tests.” Specify prerequisites, environment, fixtures or corpus, expected result, and what a failure disproves.

Match checks to the claim:

- Use hashes or canonical serialization for exact identity.
- Use parser and type checks for structural compatibility.
- Use characterization and golden tests to capture current observable behavior.
- Use differential execution to compare old and proposed paths over recorded and generated inputs.
- Use property tests for invariants and edge cases.
- Use pairwise or higher-order matrices for interacting configuration options.
- Use schema and migration compatibility checks for data contracts.
- Use visual, interaction, accessibility, viewport, and theme checks for interfaces.
- Use versioned evaluation corpora across declared model configurations for prompts.
- Use license, provenance, metadata, and rendering checks for assets and fonts.
- Run repository-required checks after targeted checks.

Limit every equivalence statement to the verified inputs, environments, versions, and tolerances. List each unrun check explicitly.
