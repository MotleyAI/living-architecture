## Context

See proposal.md (Why). `la-fetch-failed-pr-checks` is a passthrough command: both twins run their vendored copy
of `shared/scripts/fetch-failed-pr-checks.sh` (bash, `set -euo pipefail`, `gh` + `jq`), so the behaviour is
written once and the conformance corpus pins it through both twins' bins (system principle 1). Its texts
live in that shared script, like the other format-exempt review shims (principle 2).

Observed on the job from the issue (worktree-term job 122801709664):
- `gh run view --job … --log-failed` and `--log`: exit 0, empty stdout, empty stderr.
- The REST job log: 495 lines, a UTF-8 BOM before the first line, every line
  `YYYY-MM-DDTHH:MM:SS.fffffffZ <text>` except the continuation lines of a multi-line `##[error]`.
- Steps are not named in the raw log: a `run:` step's header is `##[group]Run <command>` even with a custom
  `name:`, a `uses:` step's is `##[group]Run owner/action@ref`, a composite action adds nested
  `##[group]Run …` lines, post steps log `Post job cleanup.`.
- `gh api repos/R/actions/jobs/J` gives each step's conclusion, `started_at` and `completed_at` to the second.
  The failed step 4 ran 11:58:23–11:59:04; step 3 ended and the post steps started in those same seconds.
- The section rule below isolates exactly step 4 on that log: 208 lines, from
  `##[group]Run pnpm exec vitest …` to `##[error]Process completed with exit code 1.`

Symptom and structural cause: the renderer guessed the reason for an empty excerpt from its emptiness, so a
disabled fetch, a non-Actions check and a failed fetch looked alike; and the only log provider was the run's
log zip. The fix records facts at fetch time (`log_source`, `log_attempts`) that the renderer only reports,
and adds the REST job log as a third provider.

## Goals / Non-Goals

**Goals:**
- A log excerpt for every GitHub Actions job whose log GitHub still serves.
- No guessed reasons: every empty excerpt is explained by recorded facts.

**Non-Goals:**
- No REST fallback for a run-only check (Details URL with a run and no job): the run-log endpoint returns a
  zip, and Actions CheckRuns always carry a job in their URL.
- No `##[error]`-lines composition for the `gh run view` sources; they keep their plain tail.
- No change to which checks count as failed, nor to the external-CI line of a check with no Actions run.

## Decisions

Each entry: the decision, the options weighed, the one taken and why, and who took it.

1. **Locate the failed step by the job metadata's time window, ending at the last `##[error]`** (user).
   Options: (A) the time window of the first non-success step from `gh api repos/R/actions/jobs/J`, starting
   at its first `##[group]Run ` line and ending at its last `##[error]`; (B) matching the header
   `##[group]<step name>`; (C) no section detection. Took A: B fails for any step with a custom `name:`
   and for composite actions, and C drops the issue's "failed step's section where it can be told apart".
   The `##[error]` end cuts the post-step lines that share the step's completion second: a failed `run:`
   step always ends with the runner's `##[error]Process completed with exit code N.`, a failing action
   emits its own `##[error]`.
2. **One excerpt rule for the section and the whole log** (default). `##[error]` lines before the last N
   lines, then the last N lines, in log order, each gap one `[... K lines omitted ...]` line. Over a plain
   tail of the section, a long section no longer hides an earlier error.
3. **Facts at fetch time, the renderer only reports** (default). `log_source` and `log_attempts` per
   check; the Markdown's no-excerpt line is chosen from `--max-log-lines`, the run id and the attempts,
   never from the excerpt's emptiness alone. This is the structural fix.
4. **Extension: the `<details>` summary names the source** (user, approved). The full-log fallback was
   labelled "Failed-step log", which it is not; its golden changes deliberately.
5. **Extension: a distinct `--max-log-lines 0` line** (user, approved), instead of the external-CI guess.
6. **Keep "likely an external CI" for a check with no Actions run in its Details URL** (default): there it
   is accurate, and its goldens stay.
7. **No REST fallback for run-only checks** (default): see Non-Goals.
8. **API log lines raw, BOM dropped** (default): timestamps kept, matching `gh run view` output.
9. **A new capability `failed-pr-checks` on the Python `review` node** (user, approved). `review-detection`'s
   purpose is which bots ran on a PR. Approved `architecture/model.c4` edit, Python `review` node:
   `specs ['review-detection']` → `specs ['review-detection', 'failed-pr-checks']`.
10. **A per-route `stderr` on both fake `gh` programs** (default): the conformance `FAKE_GH` and the unit-test
    `FAKE_GH`/`FakeGh.route`; documented in `conformance/README.md`.
11. **Approved SKILL.md wording** (user, approved wording), `plugin/skills/fetch-failed-pr-checks/SKILL.md`:
    - Output bullet: "…and either a log excerpt inside a collapsible `<details>` block whose summary names
      its source, or a line saying why there is none."
    - JSON schema, after `"log_excerpt": "..."`:
      `"log_source": "log-failed" | "log" | "api-step" | "api-errors-tail" | null,` and
      `"log_attempts": [{"command": "gh run view --job 67890 --log-failed", "outcome": "empty log"}]`
    - Step 3, first sentence: "The log excerpt comes from the first source that gives a log:
      `gh run view --log-failed`, then the tail of the full log (`--log`), then GitHub's job-log API sliced to
      the failed step (its `##[error]` lines plus the tail when the step can't be isolated). The `<details>`
      summary and `log_source` name the source; with no excerpt, the check lists each attempt and why it
      gave nothing."
12. **Compare timestamps on their first 19 characters** (codex). `started_at` ends in `Z`; comparing it
    whole against a 19-character log prefix drops the step's start second.
13. **Portable awk** (codex): digits spelled out instead of `{4}` intervals; the BOM built with
    `printf '\357\273\277'` and matched under `LC_ALL=C`, not `\xef` escapes — mawk and BSD awk lack both.
14. **Each `gh` call to its own stdout/stderr files** (codex):
    `if gh … >"$out" 2>"$err"; then rc=0; else rc=$?; fi`, tailed afterwards, so `pipefail` never reports
    `tail`'s status or aborts the script.
15. **`##[error]` matched at line start or after a space** (codex), so an untimestamped annotation counts.
16. **The failed step is the first with a conclusion other than `success`, `skipped`, `neutral` or null**
    (codex), so a timed-out or cancelled job (its running step is `cancelled`) is isolated too.
17. **Tests for the metadata branches** (codex): a conformance case with a failing metadata call and a usable
    log; unit tests for no failed step and an empty window.
18. **The metadata call is in `log_attempts`** (codex) with outcome `ok`, `no failed step`,
    `no log lines in the step's time window` or its failure reason, so the JSON explains an
    `api-errors-tail`. It never appears in the no-excerpt Markdown: it runs only on a non-empty log.
19. **Unit tests assert the `gh` calls** (codex): order, exact endpoints, and no API calls for a run-only
    check or `--max-log-lines 0`.
20. **A log with no non-whitespace character is empty** (codex), so it falls through to the next source.
21. **One per-run temp directory with one `EXIT` trap** (codex); the final JSON stays outside it.
22. **The section starts at the first `##[group]Run ` line in the window** (codex, from finding 7): a test
    pins a composite action's nested `##[group]Run` inside the failed step.
23. **`--max-log-lines` stays the tail size, not a strict budget** — rejected (codex, finding 4): the issue
    says "its `##[error]` lines plus the last `--max-log-lines` lines". The usage line becomes
    `tail each failed job's log excerpt at N lines (default: 200); a job-log API excerpt also keeps the earlier ##[error] lines`.
24. **Keep the errors-plus-tail rule inside an isolated section** — rejected (codex, finding 5): a section
    longer than N is tailed anyway, and keeping its earlier `##[error]` lines only adds information
    (decision 2).
25. **Claim `api-step` only on unambiguous step boundaries** — rejected (codex, finding 6): on the issue's own
    job the previous step ends in the failed step's start second, so that test would reject the very case
    being fixed; the `##[group]Run ` start rule handles it. Remaining blur is under Risks.
26. **Extra step-boundary markers** — rejected (codex, rest of finding 7): a `uses:` step's header is
    `##[group]Run owner/action@ref`, and a failure before any header (Set up job) already starts at the
    window's first line.

## Risks / Trade-offs

- [A step that runs after the failure (`if: always()` or a post step) logs an `##[error]` in the failed
  step's completion second] → the section runs on to that line; it only adds trailing lines, and the
  failure itself stays in the excerpt while the section is at most N lines past it.
- [A composite sub-step of the previous step starts a `##[group]Run ` in the failed step's start second] →
  the section starts a few lines early; it only adds leading lines.
- [Logs expired or not yet available (HTTP 404/410)] → the attempt's reason says so.
- [The whole API log is held in a temp file] → bounded by GitHub's job-log size; removed by the trap.
