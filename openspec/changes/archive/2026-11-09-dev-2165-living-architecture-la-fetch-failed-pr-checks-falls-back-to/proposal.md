## Why

On worktree-term PR 17, `la-fetch-failed-pr-checks` reported a plain GitHub Actions job (`vitest (2)`, job
122801709664, failed in step 4) as "likely an external CI". `gh run view --job <id> --log-failed` and `--log`
both exited 0 with empty output, while the REST job-log endpoint returned the full log with the failure. The
script has a single log provider (the run's log zip that `gh run view` parses), and its renderer guesses why
an excerpt is empty from the emptiness alone.

## What Changes

- When both `gh run view` attempts give no log for a job, fetch the job log from
  `gh api repos/<repo>/actions/jobs/<id>/logs`. The excerpt is the failed step's section (located by the
  job's step metadata), else the whole job log; either way its `##[error]` lines plus the last
  `--max-log-lines` lines, gaps marked.
- Every check's JSON records where its excerpt came from (`log_source`) and every attempt with its outcome
  (`log_attempts`); the Markdown reports these facts instead of guessing.
- The `<details>` summary names the excerpt's source; the full-log fallback is now labelled "Full log"
  instead of "Failed-step log".
- With no excerpt, the check lists each attempt and why it gave nothing (its error, or "empty log");
  `--max-log-lines 0` says log fetching is off. Only a check with no GitHub Actions run in its Details URL
  keeps the "likely an external CI" line.
- A log of only whitespace counts as empty and falls through to the next attempt.
- The fake `gh` of both test harnesses gains a per-route `stderr`.

## Capabilities

### New Capabilities
- `failed-pr-checks`: how `la-fetch-failed-pr-checks` obtains, slices and reports the log excerpt of each
  failed check, and how it explains a missing one.

### Modified Capabilities

## Impact

- `shared/scripts/fetch-failed-pr-checks.sh` and its vendored copies in both twins (`scripts/sync-shared`).
- Conformance: new `shim-fetch-failed-pr-checks-*` cases; the `full-log-fallback` golden changes its label.
- Test harnesses: `python/tests/test_conformance.py`, `python/tests/conftest.py`, `conformance/README.md`.
- `architecture/model.c4`: the Python `review` node also maps the `failed-pr-checks` spec.
- `plugin/skills/fetch-failed-pr-checks/SKILL.md`: output, JSON schema and source order.
