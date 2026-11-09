## 1. Test harness

- [x] 1.1 Both fake `gh` programs write an optional per-route `stderr` before exiting: the conformance `FAKE_GH` in
  `python/tests/test_conformance.py` and `FAKE_GH` + `FakeGh.route` in `python/tests/conftest.py` (route tuples or
  keyword for stderr, existing callers unchanged). Document it in `conformance/README.md`'s `gh:` line
  (`gh: [{match: [argv tokens], stdout: text-or-json, stderr: text, exit: 0}]`). Verify every existing test and
  conformance case still passes.

## 2. Tests (pr-tests stage; failing until implemented)

Fixture log lines use the real format `YYYY-MM-DDTHH:MM:SS.fffffffZ <text>`; step metadata is the
`gh api repos/o/r/actions/jobs/22` JSON (`{"steps": [{"number", "name", "conclusion", "started_at", "completed_at"}]}`,
times like `2026-01-01T00:00:10Z`), served through the fake's `--jq` support.

- [x] 2.1 Neutral conformance case `shim-fetch-failed-pr-checks-api-step`: both `gh run view --job 22` attempts
  empty; the API log starts with a UTF-8 BOM and holds three steps; step 2 (`failure`) starts in the same second as
  step 1's last lines, contains a composite action's nested `##[group]Run ` line, and ends with a multi-line
  `##[error]` whose continuation lines have no timestamp, followed by post-step lines in its completion second.
  Golden: summary `Failed-step log from the job-log API (##[error] lines + last N lines)`, excerpt from step 2's own
  header to its last `##[error]` line, BOM gone.
- [x] 2.2 Neutral case `shim-fetch-failed-pr-checks-api-errors-tail`: metadata has no failed step; the log has more
  than N lines with an early `##[error]`. Golden: the `Job log from the job-log API …` summary, the early error line,
  one `[... K lines omitted ...]` line, the last N lines.
- [x] 2.3 Neutral case `shim-fetch-failed-pr-checks-api-no-metadata`: the metadata call exits 1 with stderr, the
  log is usable. Golden: `api-errors-tail` excerpt, exit 0.
- [x] 2.4 Neutral case `shim-fetch-failed-pr-checks-no-log`: `--log-failed` exits 1 with stderr `HTTP 502`, `--log`
  empty, the API log exits 1 with `gh: Not Found (HTTP 404)`. Golden: `_No log excerpt — every attempt failed:_` and
  the three attempt lines.
- [x] 2.5 Neutral case `shim-fetch-failed-pr-checks-run-only`: a CheckRun whose Details URL is
  `https://github.com/o/r/actions/runs/11`, both `gh run view 11` attempts empty. Golden: exactly the two attempt
  lines with `empty log`.
- [x] 2.6 Neutral case `shim-fetch-failed-pr-checks-max-log-zero`: `--max-log-lines 0` with a failed Actions job.
  Golden: `_No log excerpt: log fetching is off (--max-log-lines 0)._`.
- [x] 2.7 Re-bless `shim-fetch-failed-pr-checks-full-log-fallback` (`LA_UPDATE_GOLDENS=1`; reason in the commit:
  deliberate label change) so its summary is `Full log (last 5 lines)`; review the golden diff is only that line.
- [x] 2.8 List 2.1–2.6 in `conformance/INVENTORY.md` on the fetch-failed-pr-checks row (and a row per new output
  branch: API step, API errors+tail, no-log reasons, log fetching off).
- [x] 2.9 Unit tests in `python/tests/test_review_scripts.py`, each asserting `fake_gh.calls()` (order, exact
  endpoints, `--repo o/r`) and the JSON's `log_source` / `log_attempts`:
  - API-step path: `log_source == "api-step"`, attempts `empty log`, `empty log`, `ok` (logs), `ok` (metadata);
  - whitespace-only `--log-failed` (`"\n"`) falls through to `--log`;
  - no failed step → metadata outcome `no failed step`, `api-errors-tail`;
  - failed step whose window has no log lines → `no log lines in the step's time window`, `api-errors-tail`;
  - a `cancelled` step is the failed step;
  - a step header in the same second as `started_at` (with `Z`) starts the excerpt;
  - an untimestamped `##[error]` line at line start counts as an error line;
  - metadata failure reason is its last stderr line; a non-zero exit with no stderr gives `exit <code>`;
  - a non-zero `gh run view` with stdout still gives the excerpt (`log_source == "log-failed"`);
  - run-only and `--max-log-lines 0`: no `gh api` call; `--max-log-lines 0` makes no `gh run view` call;
  - StatusContext: `log_source` null, `log_attempts` empty.
- [x] 2.10 Codex review of the tests against this change (pr-tests Step 2); resolve findings with the user.
- [x] 2.11 Neutral case `shim-fetch-failed-pr-checks-api-step-error-continuation`: step 2 is a failing action
  whose last `##[error]` spans several lines (continuation unstamped, no `Process completed` after it), followed
  by post-step lines in its completion second. Golden: the excerpt ends with the error's last continuation line.
  List it in `conformance/INVENTORY.md`.

## 3. Script

- [x] 3.1 `shared/scripts/fetch-failed-pr-checks.sh`: one per-run temp dir under `${TMPDIR:-/tmp}` with a single
  `EXIT` trap (final JSON outside it); each `gh` call as `if gh … >"$out" 2>"$err"; then rc=0; else rc=$?; fi`,
  outcome from stdout (non-whitespace), last non-empty stderr line, `exit <code>`, else `empty log`; record
  `log_attempts` (command without `--repo`) and `log_source`.
- [x] 3.2 Job-log API attempt (job id only), BOM dropped with `printf '\357\273\277'` under `LC_ALL=C`; metadata
  call picks the first step whose conclusion is not `success`/`skipped`/`neutral`/null; portable awk (digits
  spelled out, no `{n}` intervals) slices on 19-character timestamps, untimestamped lines inheriting the previous
  timestamp, from the first `##[group]Run ` to the last `^##[error]`/` ##[error]` line; fall back to the whole log;
  excerpt rule with `[... K lines omitted ...]` gaps. Verify the awk under `mawk` and `gawk` (and `busybox awk` if
  available) on the 2.1 fixture.
- [x] 3.3 Markdown: summary by `log_source`; no-excerpt lines (`--max-log-lines 0`, no run id, every attempt
  failed with one ``- `<command>`: <reason>`` line per attempt). Usage line:
  `--max-log-lines N    tail each failed job's log excerpt at N lines (default: 200); a job-log API excerpt also keeps the earlier ##[error] lines`.
- [x] 3.4 Run `scripts/sync-shared`; verify `scripts/sync-shared --check` passes and both snapshots' `CONTRACT_HASH`
  match `la-doctor --contract-hash`.

## 4. Model, skill, docs

- [x] 4.1 `architecture/model.c4`, Python `review` node: `specs ['review-detection']` →
  `specs ['review-detection', 'failed-pr-checks']` (approved, design decision 9). Verify `la-arch-check` passes.
- [x] 4.2 `plugin/skills/fetch-failed-pr-checks/SKILL.md`: apply the approved wording verbatim (design decision 11):
  output bullet, the two JSON fields, step 3's first sentence. Verify
  `npx -y @anthropic-ai/claude-code plugin validate plugin`.
- [x] 4.3 Check `docs/commands.md`, `docs/skills.md`, `plugin/skills/process-reviews/SKILL.md` for wording that now
  misdescribes the excerpt (e.g. "failed-step logs" only); raise any needed skill edit with exact wording before
  applying it.

## 5. Gates

- [x] 5.1 Python twin: `uv run pytest -q`, `uv run ruff check src tests`, `uv run basedpyright src tests`.
- [x] 5.2 npm twin: `npm run lint && npm run typecheck`, `npm test`, `npm run build && npm run conformance`.
- [x] 5.3 `scripts/conformance-cross` (every case through both twins) and `la-arch-check`.
- [x] 5.4 Reproduce on the real job: `la-fetch-failed-pr-checks 17 --repo MotleyAI/worktree-term` shows the
  `vitest (2)` excerpt from the job-log API ending at `##[error]Process completed with exit code 1.` (while GitHub
  still serves that log).
