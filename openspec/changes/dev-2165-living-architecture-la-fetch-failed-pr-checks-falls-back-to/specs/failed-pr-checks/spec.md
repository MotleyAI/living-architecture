## Purpose

Fetch the failed CI checks of a GitHub PR with a log excerpt for each GitHub Actions failure, and say
truthfully where each excerpt came from or why there is none.

## ADDED Requirements

### Requirement: Log attempts run in a fixed order until one gives a log
For each failed check whose Details URL names a GitHub Actions run, with `--max-log-lines N` greater than 0,
`la-fetch-failed-pr-checks` SHALL try these sources in order and stop at the first that gives a log:
1. `gh run view --log-failed` for the job (or for the run when the URL names no job), keeping the last N lines;
2. the same with `--log`, keeping the last N lines;
3. only when the URL names a job: the job log from `gh api repos/<repo>/actions/jobs/<job>/logs`.

A source gives a log iff its standard output has a non-whitespace character, whatever its exit code. With
`--max-log-lines 0`, or for a check whose Details URL names no GitHub Actions run, it SHALL make no log
attempt.

#### Scenario: Failed-step log first
- **WHEN** `gh run view --job 22 --log-failed` prints `step: boom`
- **THEN** the excerpt is `step: boom` and no other source is tried

#### Scenario: Full log when no step is marked failed
- **WHEN** `--log-failed` prints nothing and `--log` prints `container never started`
- **THEN** the excerpt is `container never started` and the job-log API is not called

#### Scenario: Whitespace-only output falls through
- **WHEN** `--log-failed` prints only a newline and `--log` prints `boom`
- **THEN** the excerpt is `boom`

#### Scenario: Job-log API when both gh run view attempts are empty
- **WHEN** both `gh run view` attempts for job 22 print nothing and `gh api repos/o/r/actions/jobs/22/logs` returns a log
- **THEN** the excerpt is taken from that log

#### Scenario: No API attempt for a run-only check
- **WHEN** a failed check's Details URL is `https://github.com/o/r/actions/runs/11` and both `gh run view 11` attempts print nothing
- **THEN** no `gh api` call is made

#### Scenario: Log fetching off
- **WHEN** the command runs with `--max-log-lines 0`
- **THEN** no `gh run view` or `gh api` log call is made

### Requirement: A job-log API excerpt targets the failed step
From a job log fetched from the API, a leading UTF-8 byte order mark SHALL be dropped and lines SHALL
otherwise be kept as they are. The command SHALL read the job's steps (`gh api repos/<repo>/actions/jobs/<job>`)
and take the first step whose conclusion is neither `success`, `skipped`, `neutral` nor null. Its section
SHALL be the log lines whose timestamp, to the second, lies within the step's `started_at` and
`completed_at` (a line with no timestamp takes the preceding line's), starting at the first `##[group]Run `
line among them (else the first of them) and ending at the last `##[error]` line among them (else the last
of them). When the steps cannot be read, no step qualifies, or the section is empty, the whole job log SHALL
be used instead.

From the section or the whole log, the excerpt SHALL be: all of it when it has at most N lines; otherwise
the `##[error]` lines before its last N lines, then its last N lines, in log order, with each run of omitted
lines replaced by one `[... K lines omitted ...]` line.

#### Scenario: Failed step isolated
- **WHEN** the API log holds three steps, the step metadata marks step 2 `failure`, and step 2's lines include a nested `##[group]Run ` line of a composite action
- **THEN** the excerpt starts at step 2's own `##[group]Run ` line and ends at its last `##[error]` line

#### Scenario: Step header in the step's start second
- **WHEN** the failed step's header line has the same second as its `started_at` and the previous step's last lines share that second
- **THEN** the excerpt starts at the header line

#### Scenario: Untimestamped error continuation kept
- **WHEN** the failed step's last `##[error]` message spans several lines, only the first with a timestamp
- **THEN** the excerpt keeps the lines up to the last `##[error]` line, as in the log

#### Scenario: Cancelled step counts as the failed step
- **WHEN** the job timed out and its running step has conclusion `cancelled`
- **THEN** the excerpt is that step's section

#### Scenario: No failed step in the metadata
- **WHEN** every step in the metadata succeeded and the job log has more than N lines with an early `##[error]` line
- **THEN** the excerpt is that `##[error]` line, a `[... K lines omitted ...]` line and the log's last N lines

#### Scenario: Step metadata unreadable
- **WHEN** `gh api repos/o/r/actions/jobs/22` fails and the job log is non-empty
- **THEN** the excerpt is taken from the whole job log and the command exits 0

### Requirement: The source and every attempt are recorded
Each failed check in the JSON output SHALL carry `log_source`, one of `log-failed`, `log`, `api-step`,
`api-errors-tail` or null, and `log_attempts`, the ordered list of every call made for its log, each as
`{"command": <the command without --repo>, "outcome": <"ok" or a reason>}`. The step-metadata call SHALL be
listed with outcome `ok`, `no failed step`, `no log lines in the step's time window`, or its failure reason. A
failure reason SHALL be the last non-empty line of the call's standard error, else `exit <code>` for a
non-zero exit, else `empty log`.

#### Scenario: Attempts of an API-step excerpt
- **WHEN** both `gh run view` attempts for job 22 print nothing and the API log and step metadata isolate a failed step
- **THEN** `log_source` is `api-step` and `log_attempts` lists `gh run view --job 22 --log-failed` and `gh run view --job 22 --log` with outcome `empty log`, then `gh api repos/o/r/actions/jobs/22/logs` and `gh api repos/o/r/actions/jobs/22` with outcome `ok`

#### Scenario: A gh error is the reason
- **WHEN** `gh api repos/o/r/actions/jobs/22/logs` exits 1 with `gh: Not Found (HTTP 404)` on standard error
- **THEN** its attempt's outcome is `gh: Not Found (HTTP 404)`

#### Scenario: No attempts for a non-Actions check
- **WHEN** a failed StatusContext has Details URL `https://ci.example/1`
- **THEN** its `log_source` is null and its `log_attempts` is empty

### Requirement: The Markdown names the excerpt's source or says why there is none
A check with an excerpt SHALL show it in a `<details>` block whose summary is, by `log_source`:
`log-failed`: `Failed-step log (last N lines)`; `log`: `Full log (last N lines)`; `api-step`:
`Failed-step log from the job-log API (##[error] lines + last N lines)`; `api-errors-tail`:
`Job log from the job-log API (##[error] lines + last N lines)`. A check without one SHALL show, instead:
with `--max-log-lines 0`, `_No log excerpt: log fetching is off (--max-log-lines 0)._`; for a check whose
Details URL names no GitHub Actions run, `_No log excerpt available — likely an external CI; follow Details URL._`;
otherwise `_No log excerpt — every attempt failed:_` followed by one ``- `<command>`: <reason>`` line per attempt.

#### Scenario: Full-log label
- **WHEN** the excerpt came from `gh run view --log` with `--max-log-lines 5`
- **THEN** its summary is `Full log (last 5 lines)`

#### Scenario: Every attempt failed
- **WHEN** `--log-failed` exits 1 with `HTTP 502` on standard error, `--log` prints nothing, and the job-log API fails with `gh: Not Found (HTTP 404)`
- **THEN** the check shows `_No log excerpt — every attempt failed:_` and the lines ``- `gh run view --job 22 --log-failed`: HTTP 502``, ``- `gh run view --job 22 --log`: empty log`` and ``- `gh api repos/o/r/actions/jobs/22/logs`: gh: Not Found (HTTP 404)``

#### Scenario: Run-only check with no log
- **WHEN** a check's Details URL names run 11 and no job, and both `gh run view 11` attempts print nothing
- **THEN** the check lists exactly the two `gh run view 11` attempts with reason `empty log`

#### Scenario: Log fetching off
- **WHEN** the command runs with `--max-log-lines 0` and a GitHub Actions job failed
- **THEN** the check shows `_No log excerpt: log fetching is off (--max-log-lines 0)._`

#### Scenario: External CI
- **WHEN** a failed StatusContext has Details URL `https://ci.example/1`
- **THEN** the check shows `_No log excerpt available — likely an external CI; follow Details URL._`
