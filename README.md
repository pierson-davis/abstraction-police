# Abstraction Police

An agent skill that audits a repository for duplicated or latently similar artifacts and then decides, with cited evidence, whether they deserve one abstraction or a deliberate separation. It runs under any agent that reads the Agent Skills format (Claude Code, Codex CLI, and others). The skill is instructions plus Python standard-library scripts; it calls no model API and no network.

[![eval](https://github.com/pierson-davis/abstraction-police/actions/workflows/eval.yml/badge.svg)](https://github.com/pierson-davis/abstraction-police/actions/workflows/eval.yml)
[![license: MIT](https://img.shields.io/badge/license-MIT-black.svg)](LICENSE)

## Why this exists

Agents are quick to merge code that merely looks alike. Two retry helpers with the same shape get combined; two validators that happen to share a regex get "centralized"; two design tokens with the same hex become one token, and a month later a product team cannot change one without breaking the other. Resemblance is cheap to detect and expensive to act on.

The name is Boris Cherny's: at YC Startup School in 2026 he described an "abstraction police" routine that finds near-duplicate abstractions and unifies them (see Acknowledgments). This skill makes the model prove it before it does. Detection is deterministic and candidate-only. Every claim about what the artifacts mean is bounded by the evidence that backs it. Every recommendation passes six gates, and every count in the report comes from a command the reader can re-run. The default output of an audit is a validated JSON document; the validator rejects the document if a single rule is broken, and it rejects the wording "behaviorally equivalent" unless a differential test, contract test, or runtime trace backs it.

## What an audit produces

1. `evidence.json` from `scripts/collect_evidence.py`: exact-file duplicates, repeated normalized literals, font-family values, repeated document blocks, recursive JSON shapes, and Type-2 token-block clones, all as candidates with root-relative paths. Nested git checkouts and worktrees are pruned and disclosed; symbolic links are never followed and are disclosed.
2. `findings.canonical.json`, validated by `scripts/validate_findings.py`: one finding per disposition, each with absolute existing locations, raw observations with the exact command that produced them, typed evidence with provenance and limitations, a bounded claim at a licensed claim level, six gate results, a verification plan, a rollback boundary, and the triage ledger that proves coverage.
3. A human-readable report that is a navigation layer over the JSON, never a looser restatement of it.
4. An immutable learning receipt, written after every run, that cannot authorize the skill to change itself.

## The method

### Evidence ceilings

Each evidence type licenses a maximum claim level. The validator enforces it.

| Evidence type (examples) | Highest claim it can support |
|---|---|
| `exact-content-hash`, `token-similarity`, `literal-overlap` | lexical-similarity |
| `ast-structural-similarity`, `schema-shape-overlap`, `workflow-step-overlap` | structural-similarity |
| `boundary-analysis`, `semantic-contract`, `git-cochange`, `authority-rule` | semantic-overlap |
| `differential-test`, `contract-test`, `runtime-trace` | behavioral-equivalence |

Twenty-five evidence types are defined in `evals/rubric.json`; the full ceiling table and the wording each rung is allowed to use are in `references/adjudication-rubric.md`.

### SQUINT gates

Every candidate passes through six independent gates, each recorded as `pass`, `fail`, or `unknown` with cited evidence. A failed hard gate is never averaged away.

| Gate | Question |
|---|---|
| **S** Shared responsibility | Do the artifacts implement the same domain concept, policy, asset, or mechanism, not just the same shape? |
| **Q** Qualified contract compatibility | Can one bounded contract preserve every required input, output, error, side effect, permission, and timing constraint? |
| **U** Unified change pressure | Do they change for the same reason, by shared requirement, source authority, or repeated co-change? Ownership is not authority. |
| **I** Intentional variation understood | Is every material difference classified as required variability, accidental drift, derivation output, or unresolved? |
| **N** Narrow generalization | Is the proposed common form the least general one that works, with no unrelated flags or option bags? |
| **T** Testable transition | Is there a concrete way to compare before and after, with exact commands, fixtures, and a bounded rollback? |

### Dispositions

Exactly one per finding: `reuse-existing`, `extract`, `centralize`, `generate`, `parity`, `link-and-monitor`, `keep`, or `needs-evidence`. `centralize`, `generate`, and `parity` require a typed, cited authority rule; a finding with no failed and no unknown gate that still wants to keep the duplication is not a finding.

### Coverage you can check

Candidates are triaged before investigation and every one ends promoted, dropped with a recorded class, or not reached. The ledger lives at `summary.triage` and the validator checks its arithmetic: `dropped + promoted + not_reached` must equal `candidates_total`, and any not-reached count must be named in the document's limitations. Ending early is allowed. Ending early silently is not.

## Install

The skill directory is this repository. Clone it where your agent looks for skills.

Claude Code:

```bash
git clone https://github.com/pierson-davis/abstraction-police ~/.claude/skills/abstraction-police
```

Codex CLI:

```bash
git clone https://github.com/pierson-davis/abstraction-police ~/.codex/skills/abstraction-police
```

Any other agent that supports the Agent Skills format: point it at `SKILL.md`. The scripts need Python 3.9 or later and nothing else.

Then ask for an audit in plain language, for example "Run a read-only abstraction-police audit of this repository and write the output to ../audit-out". The skill is read-only by default and writes evidence and reports outside the audited tree.

## Determinism and evaluation

`scripts/run_eval.py` runs five frozen public cases: four discovery fixtures compared byte-for-byte against golden scanner output, and one governance case that exercises the validator and the promotion controls with fourteen regressions. Each case runs twice under a scrubbed environment (`-I -S -B`, `PYTHONHASHSEED=0`, `LANG=C`) and must produce identical bytes and empty stderr. The suite binds the exact bytes of every evaluator input into an identity hash and the exact bytes of the whole skill tree into a subject hash, so a passing result cannot be replayed against different instructions or scripts.

```bash
python3 -B scripts/run_eval.py
```

CI runs the suite on Linux and macOS, on Python 3.9 and 3.12, and requires every result file to be byte-identical across all of them. At the 1.2.0 freeze the result bytes were also identical across Python 3.9, 3.11, and 3.12 locally, which span three Unicode database versions.

Two determinism boundaries are documented rather than hidden. Scanner normalization uses `unicodedata.normalize("NFKC")` and `str.casefold()`, so byte identity across machines assumes the same Unicode database version in Python; the public fixtures are ASCII and CI covers two Python versions. Model sampling is outside the suite entirely: model-assisted evaluation is governed by `evals/model-policy.json` and is inconclusive unless provider, immutable model revision, backend fingerprint, seed, temperature, and every input hash are recorded and unchanged.

## Governance

The skill cannot promote itself. After every run it writes a content-addressed learning receipt. A skill change starts only from an evaluation failure or an explicit user disposition, is built in a separate candidate tree, is evaluated by the public suite plus an external holdout owned by an independent grader, and is promoted only by the authorized person after the gate in `scripts/improvement.py` passes. Any change to executable evaluator code is ineligible at the local gate by design. `references/improvement-governance.md` has the full protocol and `build-record.md` records every revision, including proposals that were rejected and why.

## Layout

```
SKILL.md                        the procedure the agent follows
scripts/collect_evidence.py     deterministic candidate scanner
scripts/validate_findings.py    findings validator (the contract, enforced)
scripts/run_eval.py             frozen public evaluator
scripts/improvement.py          receipts, candidate requests, promotion gate
references/                     rubric, validator rules, worked example, detector recipes, taxonomy, sources, governance
evals/                          cases, goldens, schemas, rubric, model policy, identity manifest, governance regressions
agents/openai.yaml              Codex CLI interface metadata (ignored by other agents)
build-record.md                 revision history with recorded rejections
```

## Contributing

See `CONTRIBUTING.md`. The short version: the suite must pass before and after, two runs must be byte-identical, goldens are regenerated only when the scanner's output is meant to change, and validator rules are appended after `main()` so the line citations in `references/validator-rules.md` stay true.

## Acknowledgments

The name comes from Boris Cherny. Talking about Claude Code with Diana Hu at Y Combinator's Startup School in July 2026, he described a routine Anthropic runs across its own codebases and called it, in as many words, the "abstraction police":

> often in a big code base, there's the same abstraction and it appears multiple times. And if you squint, it actually maybe should just be the same abstraction, but over time, for whatever reason, you rebuilt it multiple ways in different parts of the code base. So Claude goes out every day across all our code bases. It finds these nearly duplicated abstractions and unifies them.

Two things in that sentence became the skill. The name is his. And "if you squint" is why the six adjudication gates spell SQUINT: the judgment call in his description is exactly the one this skill refuses to make on vibes. Where he runs the routine to unify at scale, this version is built to be conservative, to demand cited evidence for every "yes, these are one thing," and to leave copies alone when the evidence is only skin deep.

Source: [Boris Cherny: Building Claude Code](https://www.ycombinator.com/library/UN-boris-cherny-building-claude-code), Y Combinator Startup School, interviewed by Diana Hu, July 2026.

## License

MIT. See `LICENSE`.
