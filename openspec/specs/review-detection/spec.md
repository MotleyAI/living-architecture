# review-detection Specification

## Purpose
Work out from the PR itself, never from repo configuration, which review bots ran on it, so review helpers
behave correctly in any repo, configured or not.

## Requirements

### Requirement: la-pr-reviewers reports the bots that ran on a PR
`la-pr-reviewers <PR> [--repo OWNER/REPO]` SHALL print exactly one JSON document:
`{"coderabbit": <bool>, "sonar": {"present": <bool>, "project_key": <string|null>}}`.
- CodeRabbit is present iff the PR's status rollup has a CodeRabbit status check or the PR has any
  comment by the CodeRabbit bot.
- Sonar is present iff the PR's status rollup has a check whose name contains `sonar` (case-insensitive), or
  the PR's head commit has a check suite whose app slug contains `sonar` (case-insensitive), whatever that
  suite's status.
- The Sonar project key SHALL be, in order: the config's `reviewers.sonar.project_key`, else the
  `sonar.projectKey` property of `sonar-project.properties` at the repo root, else the `id` query parameter
  of the Sonar check's details URL (when the rollup has a Sonar check), else null.
- A `gh` failure SHALL exit 2 with the error on stderr and print no JSON. A missing or non-numeric PR SHALL
  be a usage error (exit 2).

#### Scenario: CodeRabbit by status check
- **WHEN** the PR's rollup has a CodeRabbit status check and the PR has no CodeRabbit comment
- **THEN** the output has `"coderabbit": true`

#### Scenario: CodeRabbit by comment before its status appears
- **WHEN** the rollup has no CodeRabbit check but the PR has a comment by the CodeRabbit bot
- **THEN** the output has `"coderabbit": true`

#### Scenario: No bots
- **WHEN** the rollup has only GitHub Actions checks, the head commit has no Sonar check suite, and the PR has no bot comments
- **THEN** the output is `{"coderabbit": false, "sonar": {"present": false, "project_key": null}}`

#### Scenario: Sonar by a pending check suite only
- **WHEN** the rollup has no Sonar check, the head commit has a `sonarqubecloud` check suite with status `queued`, and the config sets `reviewers.sonar.project_key: cfg_key`
- **THEN** the output has `"sonar": {"present": true, "project_key": "cfg_key"}`

#### Scenario: Sonar key from config
- **WHEN** a Sonar check is present, the config sets `reviewers.sonar.project_key: cfg_key`, and `sonar-project.properties` sets another key
- **THEN** `project_key` is `cfg_key`

#### Scenario: Sonar key from the properties file
- **WHEN** a Sonar check is present, the config sets no key, and `sonar-project.properties` sets `sonar.projectKey=props_key`
- **THEN** `project_key` is `props_key`

#### Scenario: Sonar key from the check URL
- **WHEN** a Sonar check is present with details URL `https://sonarcloud.io/dashboard?id=url_key&pullRequest=7` and no other key source exists
- **THEN** `project_key` is `url_key`

#### Scenario: Sonar present without a key
- **WHEN** a Sonar check is present and no key source yields a key
- **THEN** the output has `"present": true, "project_key": null`

#### Scenario: gh fails
- **WHEN** `gh` exits non-zero while reading the PR or the head commit's check suites
- **THEN** the command prints no JSON and exits 2

### Requirement: Waiting for reviews needs no configuration
`la-wait-for-reviews` SHALL NOT read the repo configuration and SHALL NOT accept `--skip-coderabbit`. Its
CodeRabbit settle stage SHALL run iff CodeRabbit is present on the PR by the same rule as `la-pr-reviewers`.
The CLI manifest SHALL have no per-command `gate` field.

#### Scenario: CodeRabbit not on the PR
- **WHEN** the PR has no CodeRabbit check and no CodeRabbit comment and the status rollup is clear
- **THEN** `la-wait-for-reviews` skips the CodeRabbit settle and exits 0

#### Scenario: CodeRabbit present by comment only
- **WHEN** the rollup is clear, has no CodeRabbit check, and the PR has a CodeRabbit summary comment whose coverage marker names the head commit
- **THEN** the settle stage runs, reports CodeRabbit reviewed the head commit, and exits 0

#### Scenario: Old flag rejected
- **WHEN** `la-wait-for-reviews 7 --skip-coderabbit` runs
- **THEN** it exits with the usage-error code

### Requirement: la-wait-for-reviews waits for a pending Sonar check suite
`la-wait-for-reviews`'s gate SHALL treat as pending, besides the non-terminal checks of the status rollup, every
check suite on the PR's head commit whose app slug contains `sonar` (case-insensitive) and whose status is not
`completed`, listed on stderr as `<slug> (check suite)`. It SHALL read the head commit and the rollup as one snapshot
and the suites for that head commit. A failed read SHALL leave the gate pending, never clear it.

#### Scenario: Queued Sonar suite without a check run
- **WHEN** the rollup has only completed checks and the head commit has a `sonarqubecloud` suite with status `queued`
- **THEN** the gate reports `sonarqubecloud (check suite)` as pending on stderr and does not clear; at the gate timeout the command exits 1

#### Scenario: Queued Sonar suite beside a completed Sonar check
- **WHEN** the rollup has a completed `SonarCloud Code Analysis` check and the head commit has a `sonarqubecloud` suite with status `queued`
- **THEN** the gate does not clear

#### Scenario: Completed Sonar suite
- **WHEN** the rollup has only completed checks and the head commit's `sonarqubecloud` suite is `completed`
- **THEN** the gate clears

#### Scenario: Suite read fails
- **WHEN** reading the head commit's check suites fails
- **THEN** the gate does not clear; at the gate timeout the command exits 1

### Requirement: la-wait-for-reviews settles CodeRabbit only on evidence for the head commit
When CodeRabbit is on the PR, `la-wait-for-reviews` SHALL decide CodeRabbit's outcome for the head commit from
evidence keyed to its SHA, never from a timestamp, and SHALL read that evidence on every poll, from the first one,
alongside the gate. The summary is the CodeRabbit comment whose body carries `summarize by coderabbit.ai`; no other
CodeRabbit comment counts. On each poll:
- **Reviewed** (wins over every other outcome): a CodeRabbit status on the head commit, anywhere in its history,
  whose description contains `Review completed`; or the summary's `final_review_risk_coverage` marker with
  `coveredCommitId` equal to the head SHA; or a CodeRabbit review with `commit_id` equal to the head SHA and a
  non-empty body.
- **Carried forward**: the head commit's latest CodeRabbit status describes `Prior review carried forward`.
- **Rate limited**: the latest CodeRabbit status describes `Review rate limited`.
- **Paused**: the latest CodeRabbit status describes `Review paused`.

Each outcome SHALL be printed as its `coderabbit-settled` item when first seen. The command SHALL exit only once the
gate has cleared for the head commit, by the outcome of that poll: 0 on reviewed or carried forward; 3 on rate
limited or paused, with the re-trigger command on stderr. With no outcome it SHALL keep polling until
`LA_WAIT_CR_SETTLE` seconds (default 600) after the gate cleared, then print the `cap` outcome, report on stderr
that it proceeds without evidence, and exit 0.

Descriptions SHALL match case-insensitively. Carried forward, rate limited and paused SHALL be concluded only from
a poll in which every read succeeded; a reviewed outcome stands on any read that succeeded. A failed read SHALL
never end the command. When the PR's head commit changes, the command SHALL print the `head-moved` item and restart
the gate and the settle for the new head commit.

#### Scenario: Placeholder summary does not settle
- **WHEN** `LA_WAIT_CR_SETTLE` is `0`, the summary is newer than the head commit but has no coverage marker, and the head commit has no CodeRabbit status or review
- **THEN** the command prints `coderabbit-settled <sha7> cap`, reports the cap on stderr, never prints a `reviewed` outcome, and exits 0

#### Scenario: Summary covers the head commit
- **WHEN** the summary's coverage marker has `coveredCommitId` equal to the head SHA
- **THEN** the command prints `coderabbit-settled <sha7> reviewed` and exits 0

#### Scenario: Completed status without coverage
- **WHEN** the head commit has a CodeRabbit status `Review completed` and the summary's marker names the previous commit
- **THEN** the command prints `coderabbit-settled <sha7> reviewed` and exits 0

#### Scenario: Review on the head commit
- **WHEN** a CodeRabbit review with a non-empty body has `commit_id` equal to the head SHA
- **THEN** the command prints `coderabbit-settled <sha7> reviewed` and exits 0

#### Scenario: Empty-body review is a thread reply
- **WHEN** `LA_WAIT_CR_SETTLE` is `0` and the only head-commit evidence is a CodeRabbit review with an empty body
- **THEN** the command prints `coderabbit-settled <sha7> cap` and exits 0 without a `reviewed` outcome

#### Scenario: Rate limited
- **WHEN** the head commit's latest CodeRabbit status is `success` with description `Review rate limited`, the summary covers the previous commit and says `Review limit reached`, and a newer CodeRabbit command reply exists
- **THEN** the command prints `coderabbit-settled <sha7> rate-limited`, reports CodeRabbit RATE LIMITED on stderr with the re-trigger command, and exits 3

#### Scenario: Rate limited while checks run
- **WHEN** `LA_WAIT_POLL_SECONDS` is `0`, the head commit's latest CodeRabbit status is `Review rate limited`, and a CheckRun is in progress on the first poll and completed on the second
- **THEN** the command prints `coderabbit-settled <sha7> rate-limited` after the first poll, and exits 3 only after the second

#### Scenario: Rate limited, then reviewed before the checks finish
- **WHEN** `LA_WAIT_POLL_SECONDS` is `0`, a CheckRun is in progress on the first two polls and completed on the third, the head commit's latest CodeRabbit status is `Review rate limited` on the first poll, and `Review completed` from the second
- **THEN** the command prints `coderabbit-settled <sha7> rate-limited` and then `coderabbit-settled <sha7> reviewed`, and exits 0

#### Scenario: Reviewed, then rate limited on the same commit
- **WHEN** the head commit's CodeRabbit statuses are, newest first, `Review rate limited` then `Review completed`
- **THEN** the command prints `coderabbit-settled <sha7> reviewed` and exits 0

#### Scenario: Latest status decides
- **WHEN** the head commit's CodeRabbit statuses are, newest first, `Review paused` then `Review rate limited`
- **THEN** the command prints `coderabbit-settled <sha7> paused`, reports reviews PAUSED on stderr, and exits 3

#### Scenario: Paused
- **WHEN** the head commit's latest CodeRabbit status is `Review paused` and no reviewed evidence exists
- **THEN** the command reports CodeRabbit reviews PAUSED on stderr with the re-trigger command and exits 3

#### Scenario: Carried forward
- **WHEN** the head commit's latest CodeRabbit status is `Prior review carried forward`
- **THEN** the command prints `coderabbit-settled <sha7> carried-forward` and exits 0

#### Scenario: Stale rate-limit text with a fresh reply
- **WHEN** `LA_WAIT_CR_SETTLE` is `0`, the summary says `Review limit reached` and covers the previous commit, a newer CodeRabbit reply exists, and the head commit has no CodeRabbit status
- **THEN** the command prints `coderabbit-settled <sha7> cap` and exits 0, not 3

#### Scenario: A failed read is no answer
- **WHEN** `LA_WAIT_CR_SETTLE` is `0` and reading the head commit's statuses fails, with no other evidence
- **THEN** the command prints `coderabbit-settled <sha7> cap` and exits 0

#### Scenario: Head moves during the settle
- **WHEN** the gate clears for one head commit and the PR's head is a different commit at the next poll
- **THEN** the command prints `head-moved <old7> <new7>` and runs the gate again for the new head commit

### Requirement: la-wait-for-reviews prints each new item once
`la-wait-for-reviews` SHALL poll the PR every `LA_WAIT_POLL_SECONDS` seconds (default 60) in one loop and, on each
poll, print to stdout one line per item it has not printed before, and nothing else; progress and diagnostics SHALL
go to stderr. `<sha7>` is the first seven characters of the head commit's SHA. The lines and their keys:

| Line | Item | Key |
|---|---|---|
| `ci-failed <sha7> <url> <name>` | a check in the head commit's rollup, other than a CodeRabbit or Sonar check (by the rules of `la-pr-reviewers`), whose conclusion or state is one of `FAILURE`, `TIMED_OUT`, `CANCELLED`, `ACTION_REQUIRED`, `STARTUP_FAILURE`, `ERROR`; `<url>` is its Details URL, `-` when it has none | a CheckRun or WorkflowRun: SHA and Details URL, else SHA and name; a StatusContext: SHA, context and `startedAt`, else SHA, context and Details URL |
| `coderabbit-comment <url>` | a PR review comment by the CodeRabbit bot (a new thread or a reply); `<url>` is its `html_url` | the comment id |
| `coderabbit-review <url>` | a PR review by the CodeRabbit bot with a non-whitespace body; `<url>` is its `html_url` | the review id |
| `sonar-done <sha7> <conclusion>` | the head commit has at least one Sonar check suite, every one is `completed`, and no Sonar check in the rollup is non-terminal; `<conclusion>` is the suites' conclusion, the first non-`success` one when they differ | the SHA |
| `coderabbit-settled <sha7> <outcome>` | an outcome of the CodeRabbit settle for the head commit: `reviewed`, `carried-forward`, `rate-limited`, `paused` or `cap` | the SHA and the outcome |
| `head-moved <old7> <new7>` | the head commit differs from the one of this run's previous poll | none: printed on every move |

CodeRabbit items SHALL be read only when CodeRabbit is on the PR; CodeRabbit issue comments are never items. An edit
to an item already printed SHALL NOT print it again.

The printed keys SHALL persist in the JSON file at `git rev-parse --git-path la/reviews/<owner>/<repo>/<PR>.json`,
so a later run prints only items no run has printed. Each write SHALL re-read the file, take the union with this
run's keys, and replace the file atomically, so keys another run wrote in the meantime survive. A missing file SHALL
count as empty; an unreadable or malformed one SHALL count as empty with a warning on stderr; a failed write SHALL
warn on stderr and the run SHALL continue. Outside a git repository the keys SHALL persist only for the run, with a
note on stderr. A failed read of a source SHALL print none of its items in that poll and SHALL NOT end the command.

#### Scenario: Failed job printed once
- **WHEN** `LA_WAIT_POLL_SECONDS` is `0`, the head commit is `abcdef0123`, the rollup's CheckRun `tests` failed with Details URL `https://github.com/o/r/actions/runs/1/job/2` on the first poll and the rollup is clear by then except for one CheckRun `lint` still in progress on two polls
- **THEN** stdout has `ci-failed abcdef0 https://github.com/o/r/actions/runs/1/job/2 tests` exactly once

#### Scenario: Re-run job is a new item
- **WHEN** the state file already holds the key of the failed `tests` job 2 on the head commit, and the rollup now shows `tests` failed with Details URL `https://github.com/o/r/actions/runs/1/job/5`
- **THEN** stdout has `ci-failed <sha7> https://github.com/o/r/actions/runs/1/job/5 tests` and no line for job 2

#### Scenario: Same-named checks are distinct items
- **WHEN** two failed CheckRuns are both named `tests`, with Details URLs ending `job/2` and `job/4`
- **THEN** stdout has one `ci-failed` line for each

#### Scenario: Re-reported external status is a new item
- **WHEN** the state file holds the key of a failed StatusContext `ext-ci` with Details URL `https://ci.example/1` and `startedAt` `2026-01-01T00:00:00Z`, and the rollup now shows it failed with the same URL and `startedAt` `2026-01-02T00:00:00Z`
- **THEN** stdout has `ci-failed <sha7> https://ci.example/1 ext-ci`

#### Scenario: Review bots are not CI
- **WHEN** the rollup has a failed CodeRabbit StatusContext and a failed `SonarCloud Code Analysis` CheckRun and no other failed check
- **THEN** stdout has no `ci-failed` line

#### Scenario: CodeRabbit comments and reviews
- **WHEN** CodeRabbit is on the PR, has review comments 11 (a thread) and 12 (a reply), a review 21 with a body, and a review 22 with an empty body, and a human has review comment 13
- **THEN** stdout has one `coderabbit-comment` line for each of 11 and 12, one `coderabbit-review` line for 21, and nothing for 13 or 22

#### Scenario: Edited comment is not printed again
- **WHEN** the state file holds the key of CodeRabbit comment 11 and comment 11 now has a later `updated_at`
- **THEN** stdout has no line for comment 11

#### Scenario: Sonar done
- **WHEN** the head commit's only Sonar check suite is `completed` with conclusion `failure` and the rollup's Sonar check is `COMPLETED`
- **THEN** stdout has `sonar-done <sha7> failure` once

#### Scenario: Sonar suite still queued
- **WHEN** the head commit's Sonar check suite is `queued`
- **THEN** stdout has no `sonar-done` line

#### Scenario: A second run prints nothing new
- **WHEN** a run printed items for the head commit and exited, and a second run sees the same PR state with the same state file
- **THEN** the second run prints no item lines and exits with the same code

#### Scenario: Keys of a concurrent run survive
- **WHEN** another run adds a key to the state file while this run is polling, and this run then writes its own keys
- **THEN** the file holds both runs' keys

#### Scenario: Malformed state file
- **WHEN** the state file holds `not json` and the rollup has a failed check
- **THEN** stderr warns about the state file, stdout prints the `ci-failed` line, and the command proceeds as with an empty file

#### Scenario: Outside a git repository
- **WHEN** the command runs with `--repo o/r` in a directory that is not a git repository and the rollup has a failed check
- **THEN** stderr notes the keys are not persisted, and stdout prints the `ci-failed` line

#### Scenario: Progress on stderr
- **WHEN** a poll finds checks still pending
- **THEN** the progress message is on stderr and stdout has no line for it
