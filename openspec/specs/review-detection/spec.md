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
`la-wait-for-reviews` Stage 0a SHALL treat as pending, besides the non-terminal checks of the status rollup, every
check suite on the PR's head commit whose app slug contains `sonar` (case-insensitive) and whose status is not
`completed`, listed as `<slug> (check suite)`. It SHALL read the head commit and the rollup as one snapshot and the
suites for that head commit. A failed read SHALL leave the gate pending, never clear it.

#### Scenario: Queued Sonar suite without a check run
- **WHEN** the rollup has only completed checks and the head commit has a `sonarqubecloud` suite with status `queued`
- **THEN** Stage 0a reports `sonarqubecloud (check suite)` as pending and does not clear; at the gate timeout it exits 1

#### Scenario: Queued Sonar suite beside a completed Sonar check
- **WHEN** the rollup has a completed `SonarCloud Code Analysis` check and the head commit has a `sonarqubecloud` suite with status `queued`
- **THEN** Stage 0a does not clear

#### Scenario: Completed Sonar suite
- **WHEN** the rollup has only completed checks and the head commit's `sonarqubecloud` suite is `completed`
- **THEN** Stage 0a clears

#### Scenario: Suite read fails
- **WHEN** reading the head commit's check suites fails
- **THEN** Stage 0a does not clear; at the gate timeout it exits 1

### Requirement: la-wait-for-reviews settles CodeRabbit only on evidence for the head commit
When CodeRabbit is on the PR, Stage 0b SHALL decide from evidence keyed to the SHA of the head commit that Stage 0a
cleared, never from a timestamp. The summary is the CodeRabbit comment whose body carries `summarize by
coderabbit.ai`; no other CodeRabbit comment counts. On each poll:
- **Reviewed** (exit 0, wins over every other outcome): a CodeRabbit status on the head commit, anywhere in its
  history, whose description contains `Review completed`; or the summary's `final_review_risk_coverage` marker
  with `coveredCommitId` equal to the head SHA; or a CodeRabbit review with `commit_id` equal to the head SHA and a
  non-empty body.
- **Carried forward** (exit 0): the head commit's latest CodeRabbit status describes `Prior review carried forward`.
- **Rate limited** (exit 3): the latest CodeRabbit status describes `Review rate limited`.
- **Paused** (exit 3): the latest CodeRabbit status describes `Review paused`.
- Otherwise it SHALL keep polling until the cap of `LA_WAIT_CR_SETTLE` seconds (default 600), then report that it
  proceeds without evidence and exit 0.

Descriptions SHALL match case-insensitively. Carried forward, rate limited and paused SHALL be concluded only from
a poll in which every read succeeded; a reviewed outcome stands on any read that succeeded. A failed read SHALL
never end the command. When the PR's head commit differs from the one Stage 0a cleared, the command SHALL report it
and restart at Stage 0a.

#### Scenario: Placeholder summary does not settle
- **WHEN** `LA_WAIT_CR_SETTLE` is `0`, the summary is newer than the head commit but has no coverage marker, and the head commit has no CodeRabbit status or review
- **THEN** the command reports the cap on stderr, never reports CodeRabbit as reviewed, and exits 0

#### Scenario: Summary covers the head commit
- **WHEN** the summary's coverage marker has `coveredCommitId` equal to the head SHA
- **THEN** the command reports CodeRabbit reviewed the head commit (summary covers HEAD) and exits 0

#### Scenario: Completed status without coverage
- **WHEN** the head commit has a CodeRabbit status `Review completed` and the summary's marker names the previous commit
- **THEN** the command reports CodeRabbit reviewed the head commit and exits 0

#### Scenario: Review on the head commit
- **WHEN** a CodeRabbit review with a non-empty body has `commit_id` equal to the head SHA
- **THEN** the command reports CodeRabbit reviewed the head commit and exits 0

#### Scenario: Empty-body review is a thread reply
- **WHEN** `LA_WAIT_CR_SETTLE` is `0` and the only head-commit evidence is a CodeRabbit review with an empty body
- **THEN** the command reports the cap and exits 0 without reporting a review

#### Scenario: Rate limited
- **WHEN** the head commit's latest CodeRabbit status is `success` with description `Review rate limited`, the summary covers the previous commit and says `Review limit reached`, and a newer CodeRabbit command reply exists
- **THEN** the command reports CodeRabbit RATE LIMITED on stderr with the re-trigger command and exits 3

#### Scenario: Reviewed, then rate limited on the same commit
- **WHEN** the head commit's CodeRabbit statuses are, newest first, `Review rate limited` then `Review completed`
- **THEN** the command reports CodeRabbit reviewed the head commit and exits 0

#### Scenario: Latest status decides
- **WHEN** the head commit's CodeRabbit statuses are, newest first, `Review paused` then `Review rate limited`
- **THEN** the command reports reviews PAUSED and exits 3

#### Scenario: Paused
- **WHEN** the head commit's latest CodeRabbit status is `Review paused` and no reviewed evidence exists
- **THEN** the command reports CodeRabbit reviews PAUSED on stderr with the re-trigger command and exits 3

#### Scenario: Carried forward
- **WHEN** the head commit's latest CodeRabbit status is `Prior review carried forward`
- **THEN** the command reports the prior review carried forward and exits 0

#### Scenario: Stale rate-limit text with a fresh reply
- **WHEN** `LA_WAIT_CR_SETTLE` is `0`, the summary says `Review limit reached` and covers the previous commit, a newer CodeRabbit reply exists, and the head commit has no CodeRabbit status
- **THEN** the command reports the cap and exits 0, not 3

#### Scenario: A failed read is no answer
- **WHEN** `LA_WAIT_CR_SETTLE` is `0` and reading the head commit's statuses fails, with no other evidence
- **THEN** the command reports the cap and exits 0

#### Scenario: Head moves during the settle
- **WHEN** Stage 0a clears for one head commit and the PR's head is a different commit at the next Stage 0b poll
- **THEN** the command reports that HEAD moved and runs Stage 0a again for the new head commit
