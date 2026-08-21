# Contributing

The skill is governed by its own evaluator. Read `references/improvement-governance.md` before proposing a change; the short version follows.

## Ground rules

- The suite must pass before and after your change: `python3 -B scripts/run_eval.py` exits 0 and prints `"status": "passed"`.
- Two runs must be byte-identical. CI runs the suite twice on Linux and macOS and compares every result file.
- Never refresh an expected output to make a failing change pass. Refresh only when the scanner's output is meant to change, and say so in the commit message and in `build-record.md`.
- Keep the scanner deterministic: sorted iteration everywhere, no absolute paths, no timestamps, UTF-8 bytes in and out. `scripts/collect_evidence.py` states the contract in its module docstring.
- `references/validator-rules.md` cites `scripts/validate_findings.py` by line number. Append new validator rules after `main()` (see `_validate_summary`) so earlier citations stay stable, and cite the new lines.

## Changing anything the evaluator freezes

The frozen identity covers `scripts/`, `evals/cases/`, `evals/expected/`, `evals/governance-cases/`, `evals/schemas/`, `evals/model-policy.json`, and `evals/rubric.json` (`REQUIRED_IDENTITY_*` in `scripts/run_eval.py`). After editing any of them:

1. If the scanner's output shape changed on purpose, regenerate the discovery goldens from the scrubbed runner so the bytes match what the suite will compare:

   ```bash
   python3 - <<'PY'
   import sys; sys.path.insert(0, "scripts")
   import run_eval
   for case in run_eval.discovery_case_ids():
       (run_eval.EXPECTED_DIRECTORY / f"{case}.json").write_bytes(run_eval.run_collector(case).stdout)
   (run_eval.EXPECTED_DIRECTORY / "governance.json").write_bytes(run_eval.run_governance().stdout)
   PY
   ```

   Review the diff of every golden by hand. Every changed line must be explained by your change.

2. Re-freeze the evaluator identity as a deliberate, separate step:

   ```bash
   python3 scripts/run_eval.py create-new-eval-identity --acknowledge-new-eval-identity
   ```

3. Run the suite twice and compare:

   ```bash
   python3 -B scripts/run_eval.py > /tmp/run-1.json
   python3 -B scripts/run_eval.py > /tmp/run-2.json
   cmp /tmp/run-1.json /tmp/run-2.json
   ```

4. Record the revision in `build-record.md`: trigger, what changed, what was rejected, and the new identity hash.

## Adding a public case

Add the fixture under `evals/cases/<name>/`, add its intent to `CASE_INTENT` in `scripts/run_eval.py`, generate its golden, then re-freeze. A case without an intent fails both the identity check and `create-new-eval-identity`.

## Scope

Pull requests that add a detector for one language, loosen a validator rule to make a document pass, or let a model grade its own output will be declined; the rejections recorded in `build-record.md` explain why.
