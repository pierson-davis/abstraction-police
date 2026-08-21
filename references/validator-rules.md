# Validator Rules

`scripts/validate_findings.py` is authoritative; this reference restates it for reading. If they disagree, the code wins and this document is the bug. Line numbers refer to that file. New rules are appended after `main()` so that earlier citations stay stable; `_validate_summary` is the first such appendix. The rules below are the semantic rules the validator enforces beyond plain shape checking; the shape itself (required keys, enums, no unknown properties) comes from `evals/schemas/findings.schema.json` and the field-by-field authoring guidance stays in `adjudication-rubric.md`.

## Contents

- [How the validator runs](#how-the-validator-runs)
- [What the schema does and does not enforce](#what-the-schema-does-and-does-not-enforce)
- [Scan roots and top-level coverage](#scan-roots-and-top-level-coverage)
- [Source objects](#source-objects)
- [Evidence items](#evidence-items)
- [Authority rules](#authority-rules)
- [Claims and claim levels](#claims-and-claim-levels)
- [Dispositions and actions](#dispositions-and-actions)
- [The keep rule and intentional duplication](#the-keep-rule-and-intentional-duplication)
- [Remaining enforced rules](#remaining-enforced-rules)

## How the validator runs

- Invocation: `validate_findings.py <findings.json> [--schema PATH] [--repo-root PATH] [--require-existing-paths | --allow-missing-paths] [--canonical-out PATH|-] [--quiet]` (`build_parser`, :1113-1139).
- The CLI defaults to `--require-existing-paths`: every cited path must exist (:1133). Use `--allow-missing-paths` only for archived findings whose cited files are no longer materialized. The `validate_document` library default is the opposite, `False` (:482).
- The validator does not stop at the first error. All errors across the whole document are accumulated and printed together, one per line, as `ERROR <json-path>: <message>` on stderr, exit 1 (:1096-1097, :1162-1165). Multiple independent defects in multiple findings surface in one run.
- Once a finding carries a valid `id`, every later error message for that finding is prefixed with it: `[AP-002] $.findings[1].disposition: ...` (:658-660). A finding whose `id` is invalid keeps the bare index prefix (`$.findings[1]...`), and the id-validity errors themselves are always emitted with the bare prefix because they fire before the prefix switches.
- Two kinds of short circuit exist. A JSON parse failure, a document that is neither an object nor an array, or a supplied schema missing an expected enum yields exactly one error and stops (:86-91, :467-474, :94-113). A malformed subtree (for example a non-object source or scanner block) suppresses only that subtree's deeper checks; sibling errors are still reported.
- A bare JSON array is accepted and silently normalized to `{"schema_version": "1.0", "findings": [...]}` (:467-474).
- On success without `--canonical-out`, it prints `valid: N finding(s)` (:1159-1160). With `--canonical-out` success is silent: exit 0, no output (:1154-1158). `--canonical-out -` writes canonical JSON to stdout.
- `--canonical-out PATH` is an exclusive write (`O_CREAT|O_EXCL`, `_write_exclusive_or_verify`, :1101-1110). A second invocation against the same path succeeds silently if the bytes are identical and otherwise fails with `<path>: refuses to overwrite different content`. This is an output-file error, not a findings error: validation has already passed by the time it fires. The canonical file is written only after a fully clean validation, so failed runs never create it; the error bites only after a green run followed by a revision. Workaround: delete or version the output path between runs. Better practice: validate without `--canonical-out` while authoring, then write the canonical file exactly once when the document is final. The immutability is deliberate; the record-audit receipt chain depends on it.

## What the schema does and does not enforce

`evals/schemas/findings.schema.json` is not executed as JSON Schema; no code in the bundle imports a schema validator. `validate_findings.py` reads the schema's `required` lists, property names (as allowed-key sets), the policy keys `x-claim-level-order`, `x-evidence-claim-ceilings`, and `x-behavioral-evidence` (:639-642), and every controlled vocabulary via `_enum` (:94-113, :495-512): `artifact_class`, `claim_level`, `confidence`, `severity`, `disposition`, `action`, `evidence.type`, `source.locator_kind`, provenance `kind`, authority-rule `kind` and `authority_basis`, squint gate `status`, risk `level`, explicit-list `mode`, scanner stderr `status`, and audit `dirty_state`. `_enum` fails closed: if the supplied schema lacks any expected enum, the whole run aborts immediately with a single error of the form `schema: $defs.<definition>.<property>.enum: expected a non-empty enum of strings`. Because `--schema` is caller-supplied, a swapped schema changes the accepted vocabulary; the kind-to-basis compatibility matrix (:433-452) and the action-to-disposition map (:1004-1015) remain hardcoded in the validator and cannot be widened by a schema.

The validator reimplements the remaining constraints directly, which produces known disagreements. Where the two differ the validator is authoritative.

Validator stricter than schema:

- `audit.date` must parse as a real calendar date via `date.fromisoformat` (:547-553). `2026-13-45` satisfies the schema pattern `^[0-9]{4}-[0-9]{2}-[0-9]{2}$` and is rejected by the validator.
- Every source-object rule in the section below (absolute, normalized, in-root, existing, whole-file hash match, line bounds within file length). The schema expresses none of them.
- `end_line` requires `start_line` (:187-188) and `locator_kind` and `locator` must be supplied together (:225-226). The schema declares no dependency between these fields.
- `execution.scan_roots` entries must be absolute and normalized, and trigger the top-level coverage check below; the schema says only non-empty strings.
- `summary.triage` arithmetic (the four sums and inequalities) and the not-reached limitation coupling are validator-only (`_validate_summary`, :1168-1268); the schema states only the key set and the non-negative integer types.

Validator looser than schema: no verified case currently remains. The formerly known laxness, duplicate `squint.<gate>.evidence_refs` accepted despite the schema's `uniqueItems`, is closed: duplicates now fail with `duplicate values are forbidden` (:911-914). The per-item `^E[1-9][0-9]*$` pattern on refs is transitively enforced because every ref must name an existing evidence id (:916-918) and every evidence id must already match that pattern (:786-787).

Do not conclude that other schema constraints are unenforced. `minItems`, `minLength`, and the id and sha256 patterns are separately reimplemented inside the validator (non-empty array and string checks throughout; `ID_PATTERN` and `SHA256_PATTERN` at :59-60).

## Scan roots and top-level coverage

`execution.scan_roots` is optional. When present it must be a non-empty array of absolute, normalized paths (:329-345; error fragments: `expected a non-empty array of absolute paths`, `must be an absolute filesystem path`, `must be normalized`).

Declaring scan roots opts in to a partition check over the audited root (:578-629). When at least one absolute scan root is declared and the root resolves to a real directory, every immediate child of `audit.root` must be either:

- covered by a scan root: the entry sits inside a scan root, or a scan root sits inside the entry (`_path_covers`, :458-464), or
- mentioned by basename, as a whole word, in `execution.requested_exclusions.items` or in the top-level `limitations.items` (:613-620).

An uncovered entry fails with `$.execution.scan_roots: top-level entry '<name>' is neither scanned, excluded, nor a stated limitation`, one error per entry. Under `--require-existing-paths`, a root that is not a directory fails with `cannot verify the top-level partition because the audited root is not a directory` (:625-629). The check is deliberately shallow: only immediate children of the root are examined, never deeper levels.

## Source objects

These rules apply identically to every source object: `finding.locations[]`, `observations[].sources[]`, and `evidence[].sources[]` (`_validate_source`, :136-238).

- `path` must be a non-empty absolute path, normalized without `.` or `..` segments, resolving inside the repository root (:162-176). The root is `--repo-root` when supplied; otherwise `audit.root` is adopted as the root (:536-542). When both are present they must resolve to the same directory (:539-540).
- `path` must exist under the CLI default `--require-existing-paths` (:177-179).
- `start_line` and `end_line` must be integers >= 1 (booleans rejected, :181-186); `end_line` requires `start_line` (:187-188) and must be >= it (:189-190).
- When the file exists, `start_line` and `end_line` are checked against the file's real line count and must not exceed it (:207-222). Error fragment: `exceeds file length`.
- `sha256`, when present, must be 64 lowercase hex characters (:191-195) and is recomputed over the entire file and compared byte for byte (:196-206). It is the digest of the whole file, never of the cited line range, even when the same source object carries line bounds. Do not hash the cited range. Error fragment: `does not match source file bytes`.
- `locator_kind` and `locator` must be supplied together or not at all (:223-226). `locator_kind` must be one of the schema's `source.locator_kind` enum: `line`, `json-pointer`, `yaml-path`, `toml-path`, `table-cell`, `page`, `frame`, `node`, `asset-id`, `symbol`, `other` (:227-229); `locator` must be non-empty (:230-231).
- Location distinctness: two locations count as distinct only when they differ in at least one of the 5-tuple `(path, start_line, end_line, locator_kind, locator)` (:232-238, :703-720). Two bare paths pointing at the same file count as one location. This matters for comparison claims (see below).

## Evidence items

- Each item requires `id`, `type`, `detail`, `sources`, `provenance`, `limitations`; `authority_rule` and `metric` are the only optional keys (:768-783).
- `id` must match `E` followed by a positive integer (`^E[1-9][0-9]*$`) and be unique within the finding (:786-791).
- `type` must be one of the 25 canonical evidence types (schema enum; ceilings in `adjudication-rubric.md`).
- `provenance` requires `kind`, `producer`, `method`, all non-empty; `kind` must be one of `deterministic-tool`, `direct-inspection`, `repository-history`, `runtime-observation`, `external-primary-source`, `human-confirmation` (`_validate_evidence_provenance`, :388-405).
- `limitations` is an explicit-list object: `mode` is `none` (with an empty `items` array) or `specified` (with at least one item); items must be unique non-empty strings (`_validate_explicit_list`, :263-288). The same shape governs top-level `limitations` and `execution.requested_exclusions`.
- `metric`, when present, requires `name` and `value`; `value` must be a string, number, or boolean, and NaN and infinity are forbidden (:241-260).
- The `authority_rule` field is allowed only on evidence of type `authority-rule` (:838-841) and is required there (:828-837).

## Authority rules

An `authority-rule` evidence item carries an `authority_rule` object with `kind`, `authority_basis`, and a non-empty `rule` (`_validate_authority_rule`, :408-455).

`kind` is one of `authoritative-derivation`, `explicit-parity-invariant`, `shared-requirement` (:426-429). `authority_basis` is one of (:430-432):

- `declared-source-of-truth`: the repository declares one artifact as the canonical origin.
- `normative-specification`: a specification or policy document requires the relationship.
- `executable-generation-rule`: a build or codegen rule mechanically derives one artifact from another.
- `contractual-invariant`: an explicit contract binds the artifacts to stay in agreement.

Ownership or maintenance responsibility alone is neither a kind nor a basis; supplying anything outside the vocabulary fails with `ownership alone is not authority`.

Kind-to-basis compatibility matrix (:433-452); pairings outside it fail with `is not valid for authority rule kind`:

| kind | permitted authority_basis |
|---|---|
| `authoritative-derivation` | `declared-source-of-truth`, `normative-specification`, `executable-generation-rule` |
| `explicit-parity-invariant` | `normative-specification`, `contractual-invariant` |
| `shared-requirement` | `declared-source-of-truth`, `normative-specification`, `contractual-invariant` |

For the dispositions that demand authority (`centralize`, `generate`, `parity`; see the table below), the qualifying authority-rule evidence id must appear in `squint.U.evidence_refs` (:1078-1082). Citing it only under S or Q is rejected: `squint.U.evidence_refs: must cite the applicable authority-rule evidence`. Additionally, those three dispositions are rejected outright when SQUINT U is `fail` (:1063-1067): `<disposition> is unsafe when SQUINT U=fail`. U may be `pass` or `unknown`, never `fail`.

## Claims and claim levels

- Ceiling rule: `claim_level` must not exceed the ceiling of the strongest declared evidence type, per `x-evidence-claim-ceilings` (:843-847). The error names the level but not which evidence type set the ceiling; consult the ceiling table in `adjudication-rubric.md`.
- Banned behavioral wording: the validator lexically screens the `claim` string with a case-insensitive regex for six phrases: `behaviorally equivalent`, `same behavior`, `identical behavior`, `semantically identical`, `semantically equivalent`, `interchangeable` (`BEHAVIOR_WORDING`, :30-41). Any match forces `claim_level` to be `behavioral-equivalence` (:848-853) or the finding fails. The error names the rule, not the offending phrase. The regex deliberately excludes nominal forms such as `behavioral equivalence` and `interchangeability`, so a bounded disclaimer like "behavioral equivalence was not tested and is not claimed" is in-bounds prose. The screen is a backstop, not the rule; the rule is the evidence ceiling above. Passing the screen does not license the claim, and the same wording is unchecked in `recommendation`, `evidence.detail`, and SQUINT rationales, where it is equally wrong. Write what the evidence shows instead: "the three sites read and write the same collection under the same key format", not "the three sites are interchangeable".
- Byte-identity wording: a second case-insensitive screen (`EXACT_IDENTITY_WORDING`, :43-58) matches these phrases in the `claim`, with hyphens or spaces interchangeable: `byte-identical`, `bit-identical`, `byte-for-byte`, `character-for-character`, `textually identical`, `identical bytes`, `the same bytes`, `verbatim`, `exact copy`, `exact copies`, `exact duplicate`, `exact duplicates`. Any match requires at least one evidence item of type `exact-content-hash` or `asset-exact-hash` (:854-860); error fragment: `byte-identity wording requires exact-content-hash or asset-exact-hash evidence`. This gate is on the cited evidence types, not on `claim_level`, because a byte-identity fact backed by an exact hash may legitimately appear inside a higher-level finding. Do not assert byte identity you have not hashed.
- `behavioral-equivalence` additionally requires at least one evidence item of type `differential-test`, `contract-test`, or `runtime-trace` (:861-865).
- Comparison claims require two distinct locations: any `claim_level` of `lexical-similarity`, `structural-similarity`, `semantic-overlap`, or `behavioral-equivalence` requires at least two locations distinct under the 5-tuple rule above (:866-872). Error: `comparison claims require two distinct locations`.

## Dispositions and actions

Beyond the gate guidance in `adjudication-rubric.md`, the validator enforces hard evidence preconditions per disposition. A disposition that recommends action is rejected unless the finding carries at least one `boundary-analysis` or `semantic-contract` evidence item (:1031-1043, error fragment: `action recommendations require boundary-analysis or semantic-contract evidence`). Similarity and structure evidence alone can describe a relationship but can never recommend one. Collect that evidence before writing the finding, not after.

| disposition | required evidence types (:1022-1043, :1056-1057) | required authority-rule kind (:1058-1077) | SQUINT requirements (:1044-1055, :1063-1067, :1083-1094) |
|---|---|---|---|
| `reuse-existing` | `existing-abstraction` AND (`boundary-analysis` OR `semantic-contract`) | none | S, Q, I, N, T all `pass` |
| `extract` | `boundary-analysis` OR `semantic-contract` | none | S, Q, I, N, T all `pass` |
| `centralize` | `boundary-analysis` OR `semantic-contract` | `authoritative-derivation` or `shared-requirement`, cited in `squint.U.evidence_refs` | S, Q, I, N, T all `pass`; U not `fail` |
| `generate` | `boundary-analysis` OR `semantic-contract` | `authoritative-derivation`, cited in `squint.U.evidence_refs` | S, Q, I, N, T all `pass`; U not `fail` |
| `parity` | `semantic-contract` | `explicit-parity-invariant` or `shared-requirement`, cited in `squint.U.evidence_refs` | S `pass` and T `pass`; U not `fail` |
| `link-and-monitor` | none | none | none (the rubric still requires recorded relationship, divergence policy, signal, and response) |
| `keep` | none | none | at least one gate `fail` (:1093-1094) |
| `needs-evidence` | none | none | at least one gate `unknown` (:1083-1087); also at least one `missing_evidence` item (:1088-1092) |

The optional `action` field, when present, must be one of ten tokens and must match the disposition exactly (:1001-1021); a mismatch fails with `<action> requires disposition <expected>, not <actual>`. The full mapping:

| action | required disposition | extra evidence required |
|---|---|---|
| `reuse-helper-or-component` | `reuse-existing` | |
| `extract-local-abstraction` | `extract` | |
| `parameterize-test` | `extract` | `test-setup-overlap` (:1024-1025) |
| `centralize-source-of-truth` | `centralize` | |
| `consolidate-dependency` | `centralize` | `dependency-capability-overlap` (:1026-1030) |
| `generate-from-schema` | `generate` | |
| `add-parity-test` | `parity` | |
| `link-contracts-or-assets` | `link-and-monitor` | |
| `no-change` | `keep` | |
| `investigate` | `needs-evidence` | |

For six of eight dispositions the action is fully determined by the disposition and carries no extra information; omit it if unsure. Only `extract` and `centralize` offer a second action, and each second action costs extra evidence as tabled. An action never overrides or widens the disposition. Note the two counterintuitive pairings: `parameterize-test` requires disposition `extract`, and `consolidate-dependency` requires `centralize`, not `reuse-existing`.

## The keep rule and intentional duplication

The validator rejects `keep` unless at least one SQUINT gate is `fail` (:1093-1094): `keep requires at least one failed SQUINT gate`. The rubric's catalogue of legitimate keep reasons (locality, independent oracle value, experimentation, trusted isolation, low change cost, licensing, incompatible contracts) includes several that do not obviously produce a gate failure. The enforced behavior wins: a finding whose gates are all pass-or-unknown with no fail cannot be `keep`.

Practical guidance. If every gate seems to pass and you still want to keep the duplication, the honest gate is usually S or N: an independent test oracle fails S because verifying and being verified are different responsibilities, and a deliberately unabstracted copy fails N because no narrow common form is being proposed. Do not reach for `link-and-monitor` as a container; it obliges you to record a divergence policy, a monitored signal, and a response, none of which an intentional test oracle wants. If a required gate is genuinely unknown rather than failed, the disposition is `needs-evidence`. If no gate fails and nothing is unknown, you have not found a finding.

## Remaining enforced rules

Every other error-emitting rule beyond shape checking, verified against the script. All are documented here and nowhere else unless noted.

| rule | trigger | error fragment | ref |
|---|---|---|---|
| schema_version literal | `schema_version` is anything but `"1.0"` | `expected '1.0'` | :522-523 |
| audit.root absolute | relative `audit.root` | `must be an absolute filesystem path` | :537-538 |
| audit.root vs --repo-root | `audit.root` resolves differently from `--repo-root` | `does not match --repo-root` | :539-540 |
| audit.revision | empty or missing revision string | `expected a non-empty string or '[unknown]'` | :543-544 |
| audit.dirty_state | value outside `clean`, `dirty`, `unknown` | `expected clean, dirty, or unknown` | :545-546 |
| audit.date real date | non-parseable ISO date | `expected a valid absolute YYYY-MM-DD date` | :547-553 |
| audit.commands | empty or non-string-array | `expected a non-empty array of command strings` | :554-555 |
| scope | empty or missing | `expected a non-empty string` | :560-561 |
| summary object | `summary` missing or not an object | `required property is missing` / `expected an object` | :517, :575-576, :1181 |
| summary keys | any key in `summary` other than `triage`, or `triage` missing | `unknown property` / `required property is missing` | :1184 |
| triage object and keys | `triage` not an object; any of `candidates_total`, `candidates_by_kind`, `dropped_by_class`, `investigated`, `promoted`, `not_reached` missing or extra | `expected an object` / `required property is missing` / `unknown property` | :1188, :1193-1199 |
| triage counts | a count that is not a non-negative integer (booleans rejected); a class map that is not an object of non-negative integers; an empty class name | `expected a non-negative integer` / `expected an object mapping class names` / `empty class name` | :1204, :1212-1223 |
| triage arithmetic | `candidates_by_kind` values not summing to `candidates_total`; `promoted` above `investigated`; `investigated + not_reached` above `candidates_total`; `dropped_by_class + promoted + not_reached` not equal to `candidates_total` | `values sum to` / `exceeds investigated` / `exceeds candidates_total` / `expected candidates_total` | :1231-1249 |
| not-reached limitation | `not_reached > 0` with no `limitations` item (mode `specified`) containing the phrase `not reached` and that count | `must contain an item with the phrase 'not reached'` | :1264-1268 |
| execution.output_directory | relative or non-normalized path | `must be an absolute filesystem path` / `must be normalized` | :315-319 |
| execution.commands | empty array or blank entries | `expected a non-empty array of commands` | :326-328 |
| execution.scan_roots shape | empty array, relative or non-normalized entries | `expected a non-empty array of absolute paths` / `must be normalized` | :329-345 |
| scan-root coverage | uncovered immediate child of the audited root | `neither scanned, excluded, nor a stated limitation` | :578-629 |
| scanner block | missing `version`, `sha256`, `options`, or `stderr` | per-key messages | :347-364 |
| scanner.sha256 | not 64 lowercase hex | `expected a lowercase sha256 hash` | :360-362 |
| scanner.stderr coupling | `status` outside `empty`/`captured`, or `empty` with content, or `captured` without content | `empty status requires empty content` / `captured status requires content` | :376-385 |
| explicit-list mode | `mode` outside `none`/`specified` | `expected none or specified` | :276-279 |
| explicit-list items | blank, non-string, or duplicate items; `none` with items; `specified` without items | `duplicate values are forbidden` / `mode none requires an empty array` / `mode specified requires at least one item` | :280-288 |
| finding id pattern | id not matching `^[A-Za-z0-9][A-Za-z0-9._:-]*$` | `invalid finding identifier` | :59, :651-653 |
| finding id uniqueness | id repeated across the document | `duplicate finding identifier` | :654-655 |
| enum fields | `artifact_class`, `claim_level`, `confidence`, `severity`, `disposition` outside their schema enums | `unsupported value` | :670-686 |
| recommendation | empty or missing | `expected a non-empty string` | :687-689 |
| string-array fields | any of `meaningful_differences`, `boundary_constraints`, `affected_consumers`, `owners`, `public_boundaries`, `missing_evidence`, `assumptions`, `exclusions` not an array of strings (empty arrays are valid and often correct, notably `owners` in repositories without ownership metadata) | `expected an array of strings` | :690-701 |
| locations non-empty | empty or missing `locations` | `expected a non-empty array` | :706-708 |
| observations shape | missing `detail`, `command`, or `sources`; blank strings; empty `sources` | per-key messages | :722-753 |
| evidence non-empty | empty or missing `evidence` | `expected a non-empty array` | :760-762 |
| squint gates | any of the six gates missing or carrying extra keys | `required property is missing` / `unknown property` | :877-886 |
| squint status | gate status outside `pass`/`fail`/`unknown` | `expected pass, fail, or unknown` | :900-902 |
| squint rationale | empty rationale on any gate | `expected a non-empty string` | :905-906 |
| squint evidence_refs unique | duplicate ref values in one gate | `duplicate values are forbidden` | :911-914 |
| squint evidence_refs known | ref naming no evidence id in the finding | `unknown IDs` | :916-918 |
| squint pass/fail cited | `pass` or `fail` with empty `evidence_refs` | `pass/fail requires cited evidence` | :919-920 |
| risk objects | `maintenance_risk` or `change_risk` missing `level` in `critical`/`high`/`medium`/`low`/`unknown` or a non-empty `rationale` | `unsupported risk level` | :922-938 |
| verification_plan | empty `steps`; any step missing any of `command`, `prerequisites`, `environment`, `fixtures`, `expected`, `failure_means`; `unrun_checks` not a string array | per-key messages | :940-982 |
| rollback | missing or blank `boundary` or `trigger`; empty `steps` | per-key messages | :984-999 |
| schema enum missing | supplied `--schema` lacks an expected vocabulary enum (aborts the whole run) | `expected a non-empty enum of strings` | :94-113, :495-512 |
| unknown properties | any extra key at any level (document, finding, source, gate, step, and every other object) | `unknown property` | :120-133 |
