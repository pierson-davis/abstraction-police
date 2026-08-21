# Artifact Taxonomy

Use this taxonomy to choose evidence, candidate boundaries, and verification. Do not infer common purpose from a shared representation.

## Contents

- [Universal distinctions](#universal-distinctions)
- [Code and queries](#code-and-queries)
- [UI components, styles, and design tokens](#ui-components-styles-and-design-tokens)
- [Fonts, images, icons, audio, and other assets](#fonts-images-icons-audio-and-other-assets)
- [Configurations, policies, and infrastructure](#configurations-policies-and-infrastructure)
- [Schemas, types, models, and mappings](#schemas-types-models-and-mappings)
- [Workflows and automations](#workflows-and-automations)
- [Prompts, templates, instructions, and rubrics](#prompts-templates-instructions-and-rubrics)
- [Tests, fixtures, examples, and documentation](#tests-fixtures-examples-and-documentation)
- [Dependencies and vendored material](#dependencies-and-vendored-material)
- [Cross-artifact families](#cross-artifact-families)

## Universal distinctions

Classify each candidate on four layers:

1. **Representation:** Compare bytes, normalized text, syntax trees, graph shape, metadata, or rendered form.
2. **Contract:** Compare accepted inputs, outputs, invariants, errors, side effects, permissions, performance constraints, and compatibility promises.
3. **Role:** Compare the domain concept, policy, owner, consumers, lifecycle, release cadence, and reason to change.
4. **Derivation:** Determine whether each artifact is authoritative, generated, mirrored, vendored, cached, compiled, or copied.

Use representation to discover candidates. Use contract, role, and derivation to adjudicate them.

## Code and queries

Include functions, methods, classes, modules, expressions, regular expressions, SQL, data transforms, and repeated protocol adapters.

- Detect exact files, repeated literals, normalized syntax, least-general structural patterns, call-graph overlap, and historical co-change.
- Compare name binding, types, state mutation, I/O, concurrency, ordering, exceptions, transactions, resource ownership, and performance constraints.
- Prefer `reuse-existing` when a suitable implementation already exists.
- Prefer `extract` when a small shared mechanism can sit behind semantically named wrappers.
- Prefer `parity` or `link-and-monitor` when platform or failure isolation requires separate implementations.
- Reject flag-heavy helpers whose parameters encode unrelated policies.

## UI components, styles, and design tokens

Include components, templates, layouts, CSS declarations, spacing and color values, typography roles, animation values, icons, and theme mappings.

- Compare component state machines, props, events, accessibility semantics, responsive behavior, token types, alias graphs, and actual consumers.
- Treat an equal color, dimension, or font name as value identity only. Keep distinct semantic tokens when their roles or change reasons differ.
- Prefer semantic aliases over replacing all equal values with one primitive.
- Verify with component tests, interaction tests, accessibility checks, supported viewport and theme matrices, and visual diffs with stated tolerances.

## Fonts, images, icons, audio, and other assets

Include identical files, transformed variants, sprites, illustrations, logos, photos, sound effects, and font binaries.

- Start with cryptographic hashes. Add robust or perceptual comparison only to find near-duplicate candidates.
- Compare provenance, license, editability, crop or rendering intent, resolution, color profile, glyph coverage, font tables, variable axes, version, and fallback behavior.
- Prefer `centralize` for one authoritative asset with identical usage constraints.
- Prefer `generate` for declared render or export variants derived from one source.
- Use `keep` when visual resemblance masks distinct rights, roles, accessibility text, or production requirements.

## Configurations, policies, and infrastructure

Include JSON, YAML, TOML, environment templates, feature flags, build settings, deployment manifests, access policies, CI jobs, and infrastructure definitions.

- Compare keys, types, defaults, constraints, inheritance, environment scope, secret handling, permissions, and valid option combinations.
- Treat an equal current value as a weak signal. Determine whether values must remain equal under future changes.
- Prefer `centralize` for one policy source consumed directly.
- Prefer `generate` when consumers require distinct syntaxes or checked-in derived files.
- Prefer `parity` when independent deployment boundaries must remain but an invariant can be tested.
- Treat permission expansion, secret movement, environment coupling, or a changed configuration space as hard risk evidence.

## Schemas, types, models, and mappings

Include database schemas, API specifications, validation schemas, event definitions, type declarations, serialization mappings, and domain models.

- Combine names with types, constraints, cardinality, nullability, units, identifiers, lifecycle, neighboring structure, and instance evidence.
- Identify the system of record and migration authority before proposing consolidation.
- Prefer `generate` when several language or transport representations derive from one authoritative schema.
- Prefer `link-and-monitor` when concepts correspond but their contracts or authorities cannot be unified.
- Verify backward and forward compatibility, migrations, serialization round trips, unknown-field behavior, and consumer contracts.

## Workflows and automations

Include CI/CD jobs, orchestration graphs, task runners, agent workflows, business processes, runbooks, and repeated command sequences.

- Compare labels, graph topology, causal behavior, inputs, outputs, retries, timeouts, cancellation, permissions, secrets, artifacts, concurrency, compensation, and failure propagation.
- Allow one-to-many and many-to-one alignments. Do not require each visible step to map to exactly one other step.
- Prefer `extract` for a callable subworkflow with a narrow typed boundary.
- Prefer `parity` when separate workflows must preserve a shared invariant.
- Verify success, failure, retry, cancellation, least-privilege, and artifact-retention paths.

## Prompts, templates, instructions, and rubrics

Include system prompts, prompt fragments, few-shot examples, response schemas, evaluation rubrics, document templates, and repeated policy text.

- Compare task signature, variables, example order, tools, model and version, decoding settings, context assembly, output schema, safety constraints, and evaluation corpus.
- Treat textual similarity as lexical evidence only. Treat model output as nondeterministic unless a bounded evaluation demonstrates otherwise.
- Prefer `centralize` for exact policy text that must remain authoritative.
- Prefer `extract` for a stable prompt module with explicit inputs and outputs.
- Prefer `parity` when channel-specific prompts remain separate but must satisfy the same rubric.
- Verify against a versioned evaluation set across declared model configurations. Keep the evaluated model output separate from the grading process.

## Tests, fixtures, examples, and documentation

Include test setup, fixtures, expected outputs, examples, tutorials, reference tables, and duplicated explanations.

- Distinguish an intentional independent test oracle from production duplication. Do not make a test call the same helper whose behavior it is meant to verify.
- Preserve examples that teach different contexts even when their code overlaps.
- Prefer builders or generated fixtures only when readability, locality, and failure diagnosis remain strong.
- Prefer `link-and-monitor` for repeated narrative that needs one canonical authority but must remain visible in several contexts.
- Verify that failures stay diagnostic and that generated documentation remains reproducible.

## Dependencies and vendored material

Include parallel libraries, wrappers, polyfills, local forks, vendored sources, lockfiles, and generated dependency metadata.

- Compare capability, supported environments, licenses, security posture, transitive footprint, version policy, and migration cost.
- Do not rewrite vendored, locked, or generated artifacts by hand.
- Prefer `reuse-existing` when an approved dependency already meets the complete contract.
- Prefer `generate` or the package manager's normal update path for derived metadata.
- Prefer `keep` when independent implementations provide intentional defense in depth, compatibility, or outage isolation.

## Cross-artifact families

Inspect relationships that cross file types, including schema to generated types, token to CSS variable, design component to implementation, API contract to client, prompt to evaluator, source asset to exports, and workflow definition to documentation.

Treat a cross-artifact family as a derivation or parity problem before treating it as a merge problem. Identify the authority, transformation, consumers, and verification boundary explicitly.
