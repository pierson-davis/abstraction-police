---
name: abstraction-police
description: Audit repositories and mixed artifact sets for duplicated or latently similar concepts that may deserve reuse, extraction, centralization, generation, parity enforcement, or explicit separation. Use when reviewing repeated code, components, design tokens, fonts, images, prompts, schemas, configurations, workflows, tests, documentation, or dependencies; investigating inconsistent copies; planning a consolidation; or checking whether a proposed abstraction is justified without over-abstracting.
---

# Abstraction Police

Find evidence that several artifacts represent one maintainable concept. Distinguish resemblance from equivalence. Prefer the smallest defensible intervention.

## Preserve the operating boundary

- Default to a read-only audit. Do not change the audited repository unless the user explicitly asks for remediation.
- Write evidence and reports only to an explicit output path outside the audited tree unless the user chooses a path inside it.
- Treat model-produced clusters, explanations, confidence, and proposed abstractions as untrusted hypotheses. Never use model output as evidence for its own claim.
- A second independent full audit is not the default remedy for uncertainty: independent runs reproduce each other's load-bearing digests while missing the same inventory facts, because correlated method gaps do not wash out across draws. Spend the second-pass budget on the step 9 re-derivation for action-forcing findings and on the step 1 partition proof instead. Commission a genuinely independent second run only when the audit will authorize an irreversible change such as a migration, a permission or secret move, or a public-interface consolidation, and brief that second agent on the artifact inventory rather than the first agent's conclusions, so its coverage is independent rather than its adjudication.
- Follow repository instructions and confidentiality boundaries. Do not inspect excluded or unauthorized material.
- State unknowns as unknowns. Do not turn missing evidence into a negative finding or a zero.
- Validation is a formation constraint, not a final check. Run it on the first finding.

## Load the decision rules

- Read [references/adjudication-rubric.md](references/adjudication-rubric.md) before classifying any candidate.
- Read [references/validator-rules.md](references/validator-rules.md) and [references/finding-example.md](references/finding-example.md) before authoring any finding. The validator enforces evidence preconditions, wording rules, and source mechanics that are cataloged there and nowhere else.
- Use [references/detector-recipes.md](references/detector-recipes.md) when adding format-native deterministic evidence beyond the bundled scanner.
- Read the applicable sections of [references/artifact-taxonomy.md](references/artifact-taxonomy.md) before interpreting a detector result.
- Read [references/primary-sources.md](references/primary-sources.md) when explaining the rationale, extending the method, or resolving an edge case.
- Read [references/improvement-governance.md](references/improvement-governance.md) before recording the required post-run improvement step.

## Run the audit

1. Resolve the directory containing this `SKILL.md` and the audited root to absolute paths. Invoke every bundled file through the resolved absolute skill path so commands remain valid from any working directory. Record `audit.root`, absolute `audit.date`, `audit.revision`, `audit.dirty_state`, every `audit.commands` entry, and requested `scope`. Record top-level `execution.output_directory`, explicit requested exclusions, scanner identity and options, scanner stderr, and all executed commands. Represent top-level limitations as `{\"mode\":\"none\",\"items\":[]}` or `{\"mode\":\"specified\",\"items\":[...]}`. Never leave the boundary implicit.

   Scope the tree before scanning. Discover what must be excluded rather than waiting for the user to name it:

   ```bash
   git -C /absolute/audit/root worktree list
   git -C /absolute/audit/root submodule status
   find /absolute/audit/root -mindepth 2 -name .git
   ```

   A nested worktree is marked by a `.git` file containing `gitdir:`, not a directory. Compare the scanner's would-be walked set against `git ls-files` grouped by top-level directory, and require a named reason for every directory that contributes untracked files. Read the workspace declaration in package.json, Cargo.toml, or go.work when one exists. Named traps: nested git worktrees, vendored or third-party copies, monorepo package duplication, generated output trees, checked-in build artifacts, and per-platform mirrors.

   Then establish the audited tree's complete top-level partition from an unbounded listing:

   ```bash
   find /absolute/audit/root -mindepth 1 -maxdepth 1 | sort
   find /absolute/audit/root -mindepth 1 -maxdepth 1 | wc -l
   ```

   Assign every listed entry to exactly one of: a scan root actually passed to a scanner, `execution.requested_exclusions`, or `limitations.items`. Root-level loose files are entries and need their own scan root; a decomposition into subdirectory scans never reaches them. Nested checkouts, worktrees, and vendored trees are exclusions with a stated reason, not omissions. Record both commands in `audit.commands` and the entry count in `scope`. Never derive an entry list or a count from output a display limit, `head`, `tail`, or a pager may have truncated. When any scan decision loses cross-tree detection, record that as a `limitations` item with `mode: "specified"` before running anything, not after.
2. Run deterministic collection before semantic review:

   ```bash
   python3 /absolute/path/to/abstraction-police/scripts/collect_evidence.py \
     /absolute/audit/root --output /absolute/output/evidence.json
   ```

   Run the resolved `scripts/collect_evidence.py --help` before changing literal or text-block thresholds. Pass every step-1 exclusion to the scanner with `--exclude` rather than decomposing into per-subtree scans; decomposition destroys cross-tree detection, and when it is unavoidable, record that loss as a `limitations` item. Record the exact command, scanner version or file hash, options, and stderr. Preserve scanner root-relative paths as reproducible raw evidence, but resolve and normalize every final finding location to an absolute path. Treat scanner output as candidate evidence only. The scanner never follows symbolic links; it lists every skipped link under `scan.skipped_symlinks`. Give each one a home: scan its target as its own root, exclude it with a stated reason, or record it as a `limitations` item.
3. Add format-native deterministic evidence where the scanner lacks coverage, using the runnable recipes in [references/detector-recipes.md](references/detector-recipes.md). Record every command and preserve its raw output. Record commands in re-runnable form with resolved absolute paths; a paraphrase or a placeholder is not a command. Do not let a model silently substitute for a missing parser, comparator, type checker, or test.
4. Triage candidates, sweep cross-artifact families, then form candidate groups.

   Triage before investigating: rank every scanner candidate by distinct-file count descending, then by cross-directory span, then by cross-language span. This rank is an investigation order, not a risk order; risk is assigned later per the rubric, which forbids using duplication volume alone. Drop, and record the class of, candidates that are: single-file; platform or SDK vocabulary such as framework identifiers, symbol names, MIME types, and header names; tool-fixed file formats such as asset catalogs, lockfiles, and generated manifests, where the shape is defined by a tool rather than by duplication; test-fixture content per the taxonomy's tests section; or inside an excluded subtree. Drop classes are heuristics: record drops, never declare them impossible findings. Investigate survivors in rank order and give each an outcome: promoted, dropped-with-class, or not-reached. Record the ledger under top-level `summary.triage` as `{candidates_total, candidates_by_kind, dropped_by_class, investigated, promoted, not_reached}`, and when `not_reached > 0`, add a matching `limitations` item naming the count and the rank cutoff. The validator requires `summary.triage` and checks the ledger: `candidates_by_kind` sums to `candidates_total`; `dropped_by_class` totals plus `promoted` plus `not_reached` equal `candidates_total`; `promoted` never exceeds `investigated`; and when `not_reached > 0`, some `limitations` item contains the phrase `not reached` and that count.

   The audit is complete when every candidate above the declared cutoff has a recorded outcome and the not-reached count is stated in `limitations`. Do not target a number of findings; the count is not a quality signal. A gate result is also a stopping decision: assign `keep` on a failed hard gate and `needs-evidence` on an unresolvable one per the rubric's gate interpretation, then move to the next candidate. Ending early is acceptable; ending early silently is not.

   Run one explicit cross-artifact sweep before adjudicating. Walk the families in the taxonomy's cross-artifact section, searching by counterpart name, by comments that declare mirroring or authority (`mirrors`, `matches`, `keep in sync`, `source of truth`, `owns the canonical`), and by shared identifier vocabulary across languages. The bundled scanner compares representations inside one root and cannot align an implementation with its cross-language counterpart; these candidates come from targeted commands only. Record the sweep's commands in `execution.commands` even when it finds nothing, so an empty result is evidence rather than an untested assumption.

   Form candidate groups. Cite every member by exact absolute path plus the narrowest stable locator available, such as line, symbol, JSON Pointer, YAML path, table and column, page, frame, node, or asset identifier. A candidate group is a detection unit, not a finding. Its boundary stays provisional until step 7.
5. Separate observations from interpretations. Apply the claim ceilings in the rubric to both `claim_level` and the wording of the `claim` sentence. Give every evidence item typed provenance and an explicit limitations object. Label unsupported semantic reasoning as a hypothesis requiring evidence.
6. Apply every SQUINT gate independently. Record `pass`, `fail`, or `unknown` with evidence for each letter. Do not average away a failed hard gate. For `centralize`, `generate`, or `parity`, cite a typed `authority-rule` item that states the authoritative derivation, explicit parity invariant, or shared normative requirement. Ownership, maintenance preference, and a bare `U` pass are not authority.
7. Assign exactly one primary disposition: `reuse-existing`, `extract`, `centralize`, `generate`, `parity`, `link-and-monitor`, `keep`, or `needs-evidence`. Describe any optional implementation pattern separately. Before assigning, re-cut the candidate group: if its members would take different dispositions, split it into one finding per disposition and repeat steps 5 and 6 for each. Two signals require the re-cut: a claim, gate rationale, or recommendation that silently narrows to a subset of the cited locations, and one that ranges over artifacts no location cites. Either way the finding and its cited locations must end up coextensive.
8. Specify an exact verification plan before recommending a change. First harvest the audited repository's own runnable checks, such as Makefile targets, package scripts, CI workflow steps, and test plans, and cite them in the plan instead of inventing commands. Name the commands, fixtures, environments, expected invariants, affected consumers, failure conditions, and rollback boundary. Do not claim behavioral equivalence beyond the exercised domain.
9. Validate early, re-derive, then emit.

   Validate the first complete finding before authoring the rest. Run validation on a one-finding document without `--canonical-out`:

   ```bash
   python3 /absolute/path/to/abstraction-police/scripts/validate_findings.py \
     /absolute/output/findings.json \
     --schema /absolute/path/to/abstraction-police/evals/schemas/findings.schema.json \
     --repo-root /absolute/audit/root \
     --require-existing-paths
   ```

   The validator reports every error in one pass, so one fix cycle is enough; then author the remaining findings against a shape already known to pass. Run the resolved `scripts/validate_findings.py --help` first. Stop and report a validation failure instead of bypassing it.

   Re-derive before finalizing. Your draft is model output and is not evidence for itself. For every finding whose disposition is `reuse-existing`, `extract`, `centralize`, `generate`, or `parity`, and for every finding at severity `high` or `critical` whatever its disposition: re-run each `observation.command` verbatim and confirm the output still supports `observation.detail`; re-confirm every metric value and cited line number against the current tree; re-read the `claim` and `recommendation` against the observations and delete any generalization the observations do not carry, member by member; and re-derive every document-level count from its recorded command. Findings dispositioned `keep`, `link-and-monitor`, or `needs-evidence` are exempt because they force no change. This pass re-derives what is already written; it is not a second scan. Record any command that no longer reproduces in `limitations.items`, and downgrade or correct the finding rather than keeping the stronger wording.

   Emit the canonical document once, on the final pass, by adding `--canonical-out /absolute/output/findings.canonical.json`. The flag creates the file with an exclusive write and refuses to overwrite an existing file whose bytes differ. A failed validation writes nothing, so re-running after a validation error is safe. Use `--canonical-out -` to print canonical JSON while iterating, and pass a file path only on the final emit; if the findings change after a successful emit, write to a run-numbered path.
10. Report scope and limitations first, then findings ordered by expected maintenance risk and evidence strength. Include exact existing locations, observed facts, bounded claim, SQUINT result, disposition, blast radius, verification plan, and missing evidence for every finding. A `needs-evidence` finding must list at least one specific missing item.

    Structure the human-readable report as: (1) scope and boundary, including the triage coverage statement; (2) limitations, verbatim; (3) a findings index table with id, artifact_class, distinct file count, claim_level, disposition, and maintenance_risk; (4) finding detail in index order per the content requirements already stated in this step, referencing the verification plan by finding id rather than reprinting every step; (5) aggregated `unrun_checks`. The JSON document is authoritative; the report is a navigation layer over it, and its prose is bound by the rubric's claim-wording ceilings.

## Keep remediation separate

- Require explicit authorization before applying a finding.
- Re-open the cited locations immediately before editing and preserve unrelated changes.
- Apply one coherent disposition at a time. Run the stated verification plan and repository checks.
- Report verified behavior, residual uncertainty, and every check not run. Never describe a passing syntax or snapshot check as proof of general behavioral equivalence.

## Improve after every run

- Execute the post-run process in [references/improvement-governance.md](references/improvement-governance.md) after every completed, incomplete, failed, or zero-finding run.
- Use the resolved `scripts/improvement.py --help`, then write an immutable non-authorizing learning receipt:

  ```bash
  python3 /absolute/path/to/abstraction-police/scripts/improvement.py record-audit \
    --skill-root /absolute/path/to/abstraction-police \
    --findings /absolute/output/findings.canonical.json \
    --evidence /absolute/output/evidence.json \
    --outcome completed \
    --producer-id audit-producer-1 \
    --out-dir /absolute/output/audit-learning
  ```

- Use `--outcome incomplete` or `--outcome failed` when applicable, and state explicit limitations. A zero-finding completed audit still requires a receipt. Optional validated failures or explicit user dispositions may be attached, but the receipt never authorizes a candidate by itself.
- Use `record-run` only for base or candidate evaluation evidence. Propose a skill change only from an evaluation failure or explicit user disposition, through the prescribed `propose` command.
- Never modify this live skill, its thresholds, schemas, fixtures, or expected answers during the run being evaluated.
- Never allow a candidate revision or its producing model to grade that revision. Require deterministic public and holdout evaluation, an independent grader, and explicit approval before later promotion.
- Treat the local promotion gate as fail-closed process hygiene, not an operating-system sandbox. It may rerun a candidate only when all files under `scripts/**` and `evals/governance-cases/**` exactly match the trusted live skill. Send any executable evaluator change to an externally isolated and authenticated manual baseline-adoption process.
- Run `python3 -B /absolute/path/to/abstraction-police/scripts/run_eval.py` after authorized skill changes. Require two byte-identical full-suite outputs, exact expected-JSON matches, and a passed full-tree subject identity; do not refresh expected outputs merely to make a candidate pass.
