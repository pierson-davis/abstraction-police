# Detector Recipes

Use this reference to discharge SKILL.md step 3: add format-native deterministic evidence where the bundled scanner lacks coverage. The bundled scanner (`scripts/collect_evidence.py`) emits a fixed set of candidate detectors; run it with `--help` for the current list and treat everything it cannot produce as your responsibility. Each recipe below produces one canonical evidence type from the rubric, at that type's claim ceiling, using only the standard library or tools already present on the machine.

See references/validator-rules.md for the evidence preconditions that gate dispositions.

## Contents

- [Ground rules for every recipe](#ground-rules-for-every-recipe)
- [Evidence integrity preconditions](#evidence-integrity-preconditions)
- [Method must earn the type](#method-must-earn-the-type)
- [Recipes](#recipes)
- [Harvest the repository's own checks](#harvest-the-repositorys-own-checks)
- [Beyond these recipes](#beyond-these-recipes)

## Ground rules for every recipe

- Write helper scripts into the audit's output directory, never into the skill tree and never into the audited tree.
- No network access, no package installation, and no execution of audited code. Use an external tool only when it is already installed, invoked at a pinned version, and recorded by name and version the same way the bundled scanner is. When the strong tool is unavailable, run the fallback recipe and record the weaker evidence type.
- Record for every invocation: the exact command with all options, the tool identity and version (or file sha256 for a script you wrote), stderr content even when empty, and wall time.
- Give every evidence item the schema's provenance triple: `kind`, `producer`, `method`. Use kind `deterministic-tool` for scripted comparison, `repository-history` for git-derived evidence, `direct-inspection` for manifest and declaration reading.
- Copy the claim ceiling from the rubric table verbatim. A recipe's output never supports a claim above its type's ceiling, and per-item limitations can force it lower.

## Evidence integrity preconditions

Apply these four rules before trusting any detector output, including the bundled scanner's.

1. **Establish scope before claiming a detector ran over a tree.** Enumerate nested working copies first: `git -C ROOT worktree list`, `git -C ROOT submodule status`, and `find ROOT -mindepth 2 -name .git` (a nested worktree is marked by a `.git` file containing `gitdir:`). Any directory holding a second working tree is a near-copy of the repository and multiplies every candidate. When exclusions force per-subtree scans, record in `limitations` that cross-subtree candidates were not detected and name the tree pairs never compared. Never state that a detector covered a tree it only covered part of.
2. **Guard against short reads.** A detector that read 0 bytes, or fewer bytes than `os.stat().st_size` reports, must not emit evidence for that file. On cloud-synced volumes an evicted placeholder can read empty while stat reports the true size, so every evicted file hashes identically and fabricates duplicate groups. Key exact-hash groups on `(size, digest)`, not digest alone, and report skipped files explicitly with the remedy (`brctl download` on macOS) instead of dropping them silently.
3. **Suppress nested units.** When one unit's line span encloses another's in the same file, they are not independent duplication; a closure that is the whole body of its parent scores near-identical to it by construction. Do not emit both a file-level and an enclosing-directory-level claim for the same bytes. Report the suppressed count so a reader knows the filter ran.
4. **A shared file format is not duplication.** Tool-fixed formats (asset catalogs, lockfiles, generated manifests, IDE project files) match structurally across unrelated instances by construction. Before filing any key-shape or schema-shape candidate, check the taxonomy's derivation layer: is the key set chosen by an author or imposed by a tool? If key overlap is high, value overlap is low, and the format is tool-fixed, the correct disposition is `keep` with the fixed format recorded as the concrete reason. Values under collapsed array paths are not comparable and must never be counted as equal.

## Method must earn the type

Select the evidence type from the method that produced the observation, not from the claim you want to support. The rubric's ceiling table is keyed on the type string, so relabelling a weak method as a strong type silently buys a higher ceiling; that is the same error as citing a model as evidence. The rubric already binds claim to type ("Select a level no higher than the strongest cited canonical evidence type") and binds downgrades; this rule binds type to method.

- A textual search for a symbol name is `literal-overlap`. It becomes `call-graph` only when a resolver binds each occurrence to a declaration. Record the resolver name and version in `provenance.method`.
- A whitespace- or comment-normalized text comparison is `normalized-text-similarity`. It becomes `ast-structural-similarity` only when both sides were parsed and compared as trees or serialized parse streams. Record the parser and its version.
- A count of matching keys in two documents is `config-key-overlap`. It becomes `schema-shape-overlap` only when both documents are schemas and types, constraints, cardinality, and nullability were compared, not names alone.
- A perceptual image fingerprint is `asset-perceptual-similarity` even at Hamming distance 0. It never becomes `asset-exact-hash`.
- Tests you did not run are not evidence. Only an executed, recorded run supports `differential-test`, `contract-test`, or `runtime-trace`.

When the recipe you could run is weaker than the recipe you wanted, use the weaker type, take the lower ceiling, and record the unavailable tool under `limitations`. When in doubt between two types, record the weaker one.

## Recipes

Every recipe records: the exact command, the tool identity and version, and stderr. The per-recipe entries below add only what is specific to the method.

### `exact-content-hash`

Ceiling `lexical-similarity`. Provenance kind `deterministic-tool`.

```bash
python3 - FILE1 FILE2 ... <<'EOF'
import hashlib, os, sys
groups, skipped = {}, []
for p in sys.argv[1:]:
    data = open(p, "rb").read()
    if len(data) != os.stat(p).st_size or len(data) == 0:
        skipped.append(p); continue
    groups.setdefault((len(data), hashlib.sha256(data).hexdigest()), []).append(p)
for (size, digest), members in groups.items():
    if len(members) > 1: print("DUP", size, digest, members)
print("skipped(short-read):", skipped)
EOF
```

Record additionally: the skipped-file list. Trap: identical hashes prove byte identity only; they say nothing about shared role, license, ownership, or which copy is authoritative. Short reads on cloud-synced volumes fabricate duplicate groups; the size guard is mandatory (precondition 2).

### `normalized-text-similarity`

Ceiling `lexical-similarity`. Provenance kind `deterministic-tool`. Compare two cited line ranges after declared normalization:

```bash
python3 - "FILE_A:START-END" "FILE_B:START-END" <<'EOF'
import difflib, re, sys
def norm(spec):
    path, rng = spec.rsplit(":", 1)
    lo, hi = map(int, rng.split("-"))
    raw = open(path).read().splitlines()[lo-1:hi]
    out = []
    for ln in raw:
        ln = re.sub(r"//.*$|#.*$", "", ln)   # adjust comment syntax per language
        ln = re.sub(r"\s+", " ", ln).strip()
        if ln: out.append(ln)
    return raw, out
rawa, na = norm(sys.argv[1]); rawb, nb = norm(sys.argv[2])
print("lines_a=%d lines_b=%d" % (len(na), len(nb)),
      "ratio_norm=%.4f" % difflib.SequenceMatcher(a=na, b=nb).ratio(),
      "ratio_raw=%.4f" % difflib.SequenceMatcher(a=rawa, b=rawb).ratio(),
      "only_a=%d only_b=%d" % (sum(1 for l in na if l not in nb),
                               sum(1 for l in nb if l not in na)))
EOF
```

Record additionally: an explicit normalization statement (what was folded: comments, whitespace, case). Trap: this method is identifier-sensitive; a systematically renamed copy scores low here while an identifier-erasing structural comparison groups it. A low ratio therefore does not refute duplication, and a high ratio driven by boilerplate (license headers, generated preludes) does not indicate it. Never record this output as `ast-structural-similarity`.

### `token-similarity`

Ceiling `lexical-similarity`. Provenance kind `deterministic-tool`. k-gram Jaccard over lexed tokens:

```bash
python3 - FILE_A FILE_B <<'EOF'
import re, sys
def grams(path, k=5):
    toks = re.findall(r"[A-Za-z_]\w*|\d+|[^\sA-Za-z_\d]", open(path).read())
    return set(tuple(toks[i:i+k]) for i in range(len(toks)-k+1))
a, b = grams(sys.argv[1]), grams(sys.argv[2])
print("jaccard=%.3f grams_a=%d grams_b=%d" % (len(a & b)/len(a | b), len(a), len(b)))
EOF
```

Record additionally: k, the tokenizer regex or lexer used, and the unit sizes. Trap: short units score high against each other by chance; gate on a minimum token count (60 is a workable floor) before reporting a pair. Renamed identifiers depress the score exactly as in the text recipe; if you erase identifiers before comparing, you have changed method and the honest label is still `token-similarity`, never a structural type, because no parse occurred.

### `ast-structural-similarity`

Ceiling `structural-similarity`. Provenance kind `deterministic-tool`. Both sides must be parsed; record the parser and version.

Python, stdlib only. Two useful normalization levels: `shape` (identifiers erased, constants reduced to type names) catches renamed copies; keeping identifiers catches value-level copies. Normalize a re-parsed copy of each unit so sibling nodes are not mutated in place:

```bash
python3 - FILE1 FILE2 ... <<'EOF'
import ast, hashlib, sys
def shape(tree):
    for n in ast.walk(tree):
        for f in ("id", "arg", "attr", "name"):
            if hasattr(n, f) and isinstance(getattr(n, f), str): setattr(n, f, "_")
        if isinstance(n, ast.Constant): n.value = type(n.value).__name__
    return ast.dump(tree, include_attributes=False)
groups = {}
for p in sys.argv[1:]:
    for node in ast.walk(ast.parse(open(p).read())):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            iso = ast.parse(ast.unparse(node))
            d = hashlib.sha256(shape(iso).encode()).hexdigest()
            groups.setdefault(d, []).append("%s:%d:%s" % (p, node.lineno, node.name))
for d, m in groups.items():
    if len(m) > 1: print("GROUP", d[:12], m)
EOF
```

Gate on a minimum node or token count (25 nodes is a workable floor) or trivial getters flood the output. `ast.unparse` requires Python 3.9+.

TypeScript and JavaScript: no stdlib parser exists. The zero-install path is the audited repository's own vendored compiler: in a Node script written to the output directory, `createRequire(REPO + "/package.json")("typescript")`, then `ts.createSourceFile(path, text, ts.ScriptTarget.Latest, true)` per file (syntax only, no program, no type check), serialize each function-like node pre-order as `ts.SyntaxKind[node.kind]` strings, and hash or Jaccard-compare the streams. Record `ts.version` from `node_modules/typescript/package.json`. When no `typescript` is vendored anywhere in scope, fall back to the normalized-text recipe and record `normalized-text-similarity`.

Swift: no stdlib parser and no zero-install option; requires macOS with Xcode. `xcrun swift-frontend -dump-parse FILE.swift` parses a single file with no build context. Two mandatory normalizations before hashing or comparing: strip `0x[0-9a-f]+` memory addresses (they differ per invocation and destroy hashing), and treat each `range=[file:1:2 - line:3:4]` attribute as one atom (it contains spaces, so a naive whitespace lexer splits it and every unit loses its line span). Without Xcode, fall back to normalized text and take the weaker type.

Trap for all languages: parse-level identity is not behavioral equivalence; two structurally identical functions can call different externals with different contracts. State similarity in the named parsed structure only.

### `control-flow-similarity`

Ceiling `structural-similarity`. Provenance kind `deterministic-tool`. Extract each unit's ordered control-flow skeleton and compare. Python version (the `getattr` guard matters; some node classes do not exist on older interpreters, and `ast.walk` is breadth-first so an explicit recursive visit is required for source order):

```bash
python3 - FILE1 FILE2 ... <<'EOF'
import ast, sys
CF = tuple(getattr(ast, n) for n in
    ("If","For","While","Try","With","Raise","Return","Break","Continue","Match")
    if hasattr(ast, n))
def skeleton(node):
    out = []
    def visit(n):
        if isinstance(n, CF): out.append(type(n).__name__)
        for c in ast.iter_child_nodes(n): visit(c)
    visit(node)
    return out
for p in sys.argv[1:]:
    for node in ast.walk(ast.parse(open(p).read())):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            print(p, node.lineno, node.name, " ".join(skeleton(node)))
EOF
```

For other languages, filter the same parse streams used by the AST recipe to control-flow node kinds. Record additionally: the kind list used. Trap: short skeletons collapse; every guard-and-return helper reads `If Return Return`. Require a minimum branch count (3 or more control-flow nodes) before citing a match, and never present skeleton identity as identical behavior; the skeleton deliberately discards every condition and every operand.

### `schema-shape-overlap`

Ceiling `structural-similarity`. Provenance kind `deterministic-tool`. Applies only when both documents are schemas (JSON Schema, API specs, validation schemas, type declarations). Compare key paths and, per shared path, declared type, constraints, cardinality, and nullability. Walk both documents, collapse array indices to `[]`, and diff the resulting path-to-declaration maps:

```bash
python3 - SCHEMA_A.json SCHEMA_B.json <<'EOF'
import json, sys
def paths(v, prefix=""):
    out = {}
    if isinstance(v, dict):
        for k, x in v.items(): out.update(paths(x, prefix + "/" + k))
    elif isinstance(v, list):
        for x in v: out.update(paths(x, prefix + "/[]"))
    else:
        out[prefix] = (type(v).__name__, v, "[]" in prefix)
    return out
a = paths(json.load(open(sys.argv[1]))); b = paths(json.load(open(sys.argv[2])))
shared = set(a) & set(b)
print("key_jaccard=%.3f" % (len(shared)/len(set(a) | set(b))),
      "type_agreement=%.3f" % (sum(1 for p in shared if a[p][0] == b[p][0])/max(len(shared),1)),
      "values_equal=%d" % sum(1 for p in shared if not a[p][2] and a[p][1] == b[p][1]),
      "values_differ=%d" % sum(1 for p in shared if not a[p][2] and a[p][1] != b[p][1]),
      "not_comparable_under_arrays=%d" % sum(1 for p in shared if a[p][2]))
EOF
```

Record additionally: which constraint dimensions were actually compared. Trap: comparing names alone is `config-key-overlap`, not this type (see Method must earn the type). Two schemas generated by the same tool share shape by construction (precondition 4). Shape agreement does not establish a shared system of record; identify migration authority separately per the taxonomy.

### `config-key-overlap`

Ceiling `structural-similarity`. Provenance kind `deterministic-tool`. Same walker as the schema recipe, applied to configuration documents, reporting key-path Jaccard and leaf-type agreement. Format bridges, all verified zero-install on macOS:

- Plist and Xcode `project.pbxproj` (OpenStep plist): `plutil -convert json -o - FILE` emits JSON on stdout.
- YAML: pyyaml when installed, otherwise system Ruby: `/usr/bin/ruby -ryaml -rjson -e 'print YAML.safe_load(File.read(ARGV[0]), aliases: true).to_json' FILE`.

Record additionally: the conversion command and converter version. Traps: both pyyaml and Ruby's psych implement YAML 1.1, so a GitHub Actions `on:` key loads as boolean `true`; do not report it as a key difference. Values under collapsed array paths are counted separately, never as equal (a colorset array holding different colors reports perfect key Jaccard). High key overlap in a tool-fixed format is the format, not duplication (precondition 4).

### `workflow-step-overlap`

Ceiling `structural-similarity`. Provenance kind `deterministic-tool`. Convert each workflow to JSON (YAML bridge above), extract the ordered step list per job, and compare step sequences:

```bash
/usr/bin/ruby -ryaml -rjson -e 'print YAML.safe_load(File.read(ARGV[0]), aliases: true).to_json' WF.yml > wf.json
python3 - wf.json <<'EOF'
import json, sys
doc = json.load(open(sys.argv[1]))
for job, spec in (doc.get("jobs") or {}).items():
    for i, step in enumerate(spec.get("steps") or []):
        print("%s[%d] %s" % (job, i, step.get("run") or step.get("uses")))
EOF
```

Compare the extracted sequences with the normalized-text or token recipe, then report overlap at the step level. Record additionally: which fields were compared (`run` bodies, `uses` references, or both). Trap: shared marketplace actions (`actions/checkout@v4` and peers) appear in nearly every workflow; they are platform vocabulary, not duplication. Weight `run` bodies over `uses` names, and remember the taxonomy allows one-to-many step alignments; do not require each step to map to exactly one counterpart.

### `test-setup-overlap`

Ceiling `structural-similarity`. Provenance kind `deterministic-tool`. Reuse the AST unit recipe filtered to test-setup units: functions named `setUp`/`setUpWithError`/`tearDown`, pytest fixtures (decorated `@pytest.fixture`), `beforeEach`/`beforeAll` callbacks, and shared fixture files. Group by shape hash or compare with the token recipe, and cite each member with file, line, and the test class or suite it serves. Record additionally: the unit-selection rule used. Trap: the taxonomy treats an intentional independent test oracle as distinct from production duplication. Duplicated setup can be deliberate isolation; never let this evidence alone drive a consolidation that would make a test call the helper whose behavior it verifies, and keep failure diagnosis in view before proposing shared builders.

### `dependency-capability-overlap`

Ceiling `structural-similarity`. Provenance kind `direct-inspection`. For each dependency in a candidate pair: read the installed manifest (`node_modules/NAME/package.json`, or the equivalent lock/metadata entry for other ecosystems) for version, license, description, and direct-dependency count; then enumerate the repository's actual import sites and the bindings actually used:

```bash
python3 -c 'import json,sys; m=json.load(open(sys.argv[1])); print(m["name"], m["version"], m.get("license"), len(m.get("dependencies",{})))' node_modules/NAME/package.json
grep -rn --include='*.ts' --include='*.js' -E "from ['\"]NAME['\"]|require\(['\"]NAME['\"]\)" SRC_DIR
```

Compare the used-binding sets, not the advertised feature lists. Record additionally: every import site cited by file and line, and the manifest paths read. Trap: capability overlap on paper (two HTTP clients, two date libraries) does not mean the used surfaces overlap; consolidation cost is a function of the bindings actually consumed. Presence in a lockfile is not usage. Declared-but-unimported dependencies are a different finding entirely.

### `git-cochange`

Ceiling `semantic-overlap`. Provenance kind `repository-history`; producer `git VERSION + cochange script`; method `single git log --name-only pass, pairwise set intersection with commit-fanout partition`.

Step 1: cache the history once per audit; it is one process, not one per path. The `\x1e` record separator is load-bearing; without it the dump parses as one commit.

```bash
git -C REPO --no-pager log --format=$'\x1e%H|%cI|%s' --name-only --no-renames > OUT/hist.txt
```

Step 2: per candidate pair, compute counts, Jaccard, and both conditional probabilities; the conditionals are asymmetric and more informative than Jaccard alone. Step 3: partition shared commits by fanout; only focused commits are evidence.

```bash
python3 - OUT/hist.txt PATH_A PATH_B <<'EOF'
import sys
FANOUT = 25
commits = []
for rec in open(sys.argv[1]).read().split("\x1e"):
    rec = rec.strip()
    if not rec: continue
    lines = rec.splitlines()
    h, date, *_ = lines[0].split("|", 2)
    files = set(l.strip() for l in lines[1:] if l.strip())
    commits.append((h, date, files))
a, b = sys.argv[2], sys.argv[3]
ca = [c for c in commits if a in c[2]]; cb = [c for c in commits if b in c[2]]
both = [c for c in commits if a in c[2] and b in c[2]]
focused = [c for c in both if len(c[2]) <= FANOUT]
union = len({c[0] for c in ca} | {c[0] for c in cb})
dates = [c[1] for c in commits]
print("commits_a=%d commits_b=%d both=%d focused=%d bulk=%d" %
      (len(ca), len(cb), len(both), len(focused), len(both) - len(focused)),
      "jaccard=%.4f" % (len(both)/union) if union else "jaccard=n/a",
      "P(b|a)=%.4f" % (len(both)/len(ca)) if ca else "P(b|a)=n/a",
      "P(a|b)=%.4f" % (len(both)/len(cb)) if cb else "P(a|b)=n/a")
print("window: commits=%d oldest=%s newest=%s" % (len(commits), min(dates), max(dates)))
if not ca or not cb:
    print("WARNING: a path has zero commits in the window; check for rename or wrong relative path")
EOF
```

Mandatory fanout rule: a shared commit touching more than the threshold (default 25 files) is a squash, a sweep, a formatting pass, or an initial import; it shows the files were in the tree at the same time, not that they change for the same reason. Never let bulk commits alone support a U-gate pass.

Mandatory limitations, recorded verbatim on the evidence item: (a) history is evidence for the inspected period only (state commit count, oldest and newest date); it is not proof of future intent, matching the rubric's U-gate text; (b) computed with `--no-renames`, so a file renamed inside the window shows artificially few commits; re-check suspicious paths with a per-path `git log --follow`; (c) squash-merge workflows collapse independent changes into one commit and inflate co-change; (d) generated, vendored, and lockfile artifacts co-change mechanically; (e) zero shared commits with both paths present in the window is evidence of independent change, not missing data; the zero-commit warning usually means an untracked path or a wrong relative path.

Interpretation: 3 or more focused shared commits materially support U; 1 to 2 are weak and need a second U signal; bulk-only sharing leaves U unknown; both paths present with zero shared commits is counter-evidence for U. Use this as a U-gate signal, not as a cheap route to a semantic-overlap ceiling; co-change never substitutes for the cited authority-rule that `centralize`, `generate`, and `parity` require.

### `call-graph`

Ceiling `semantic-overlap`. Provenance kind `deterministic-tool`; the resolver's name and version go in `provenance.method`. A grep is not a call graph: a textual search cannot distinguish two independent declarations of the same name from one shared symbol, and its honest type is `literal-overlap`. This type requires a resolver that binds each occurrence to a declaration: for TypeScript, `ts.createProgram` plus `checker.getSymbolAtLocation` (with `skipLibCheck`) over the vendored compiler; for other languages, an LSP references request or a compiler-built index. Emit, per symbol: the declaration site, every resolved reference with file and line, and the consumer count (which is what `affected_consumers` needs). Record additionally: the program or index build time. Trap: building a type-checking program is orders of magnitude slower than a syntax-only parse; run it only on an already-narrowed candidate group, never over the whole tree. When no resolver is available, run the grep, record `literal-overlap`, and take the lexical ceiling.

### `asset-exact-hash`

Ceiling `lexical-similarity`. Provenance kind `deterministic-tool`. The exact-content-hash recipe applied to binary assets, with the same `(size, digest)` group key and short-read guard; `shasum -a 256` is an acceptable producer when the guard is applied separately. Trap: byte identity says nothing about license, rights, alt text, color profile, or rendering intent; the taxonomy's asset section governs what an identical pair may mean. The short-read guard is non-negotiable for asset trees on cloud-synced volumes (precondition 2).

### `asset-perceptual-similarity`

Ceiling `lexical-similarity`. Provenance kind `deterministic-tool`. Zero-install on macOS: downscale each image to 9x9 with `sips`, then compute a 72-bit difference hash from the BMP with the standard library:

```bash
sips -s format bmp -z 9 9 IN.png --out OUT.bmp
python3 - OUT1.bmp OUT2.bmp <<'EOF'
import struct, sys
def dhash(path):
    d = open(path, "rb").read()
    off = struct.unpack("<I", d[10:14])[0]
    w, h = struct.unpack("<ii", d[18:26])
    bpp = struct.unpack("<H", d[28:30])[0] // 8
    row = (w * bpp + 3) & ~3
    px = [[sum(d[off + (h-1-y)*row + x*bpp : off + (h-1-y)*row + x*bpp + 3])
           for x in range(w)] for y in range(abs(h))]
    bits = 0
    for y in range(9):
        for x in range(8):
            bits = (bits << 1) | (px[y][x] > px[y][x+1])
    return bits
a, b = dhash(sys.argv[1]), dhash(sys.argv[2])
print("hamming=%d/72" % bin(a ^ b).count("1"))
EOF
```

Record additionally: the sips version (`sips --help` header) and the downscale dimensions. Trap: Hamming distance 0 is not identity; byte-distinct images that differ in small regions hash identically at 9x9. Never record this output as `asset-exact-hash`, and never let it support claims about rights, provenance, or rendering intent. Off macOS there is no zero-install perceptual option; use exact hashing only and record the coverage gap in `limitations`.

## Harvest the repository's own checks

Before writing any verification plan, enumerate the audited repository's own runnable checks and cite them instead of inventing commands. Harvesting proves a command exists, never that it passes; its evidence type is `inventory` at ceiling `inventory`, provenance kind `direct-inspection`. Harvesting means reading declared commands, never executing them; the read-only audit boundary holds.

Read whichever of these exist, each cited by file and line:

- `package.json` `scripts` entries at every level outside `node_modules` (emit the ready-to-paste `npm --prefix DIR run NAME`).
- Makefile and justfile targets.
- `run:` steps in `.github/workflows/*.yml` and other CI definitions; treat these as first-class, not optional.
- Fenced code blocks in CLAUDE.md, AGENTS.md, CONTRIBUTING.md, README.md, and docs indexes. Match bare ``` fences as well as language-tagged ones; authoritative build commands often sit untagged. Bare-fence matching raises recall and pulls in non-command prose, so select rather than paste wholesale.
- Xcode shared schemes under `*.xcodeproj/xcshareddata/xcschemes`, `*.xctestplan` files, pytest and tox configuration, shell scripts under `scripts/`.
- When an Xcode project is present, `xcrun simctl list devices available`, so any plan names a destination that resolves on this machine today.

Record the harvested inventory under the top-level `summary` object, which the schema leaves free-form; the `execution` block is closed to exactly `output_directory`, `requested_exclusions`, `scanner`, and `commands`, and `execution.commands` means commands actually executed during the audit.

Two rules for the resulting plan: every `verification_plan` step cites the harvested source it came from (manifest or document path and line) or is explicitly labeled as a standard tool whose availability was verified here; and when a harvested command names an environment that does not currently resolve (a simulator model, an emulator project, a required variable), substitute the resolvable value and record the substitution under `assumptions`, or move the step to `unrun_checks`. A documented command copied from a stale doc fails indistinguishably from a real regression.

## Beyond these recipes

No recipe in this file produces `differential-test`, `contract-test`, or `runtime-trace`. Those require executing the artifact, they are the only route to `behavioral-equivalence`, and a read-only audit does not run them; plan them from the harvested repository checks and list them under `unrun_checks` instead. `boundary-analysis`, `semantic-contract`, `existing-abstraction`, and `authority-rule` are direct-inspection types: quote the declaration, manifest, or rule-bearing source verbatim with file and line, and record what the source does not state as unknown rather than inferring it. See references/validator-rules.md for which dispositions require which of these types before the validator will accept a finding.
