## Purpose

Work out from the PR itself, never from repo configuration, which review bots ran on it, so review helpers
behave correctly in any repo, configured or not.

## ADDED Requirements

### Requirement: la-pr-reviewers reports the bots that ran on a PR
`la-pr-reviewers <PR> [--repo OWNER/REPO]` SHALL print exactly one JSON document:
`{"coderabbit": <bool>, "sonar": {"present": <bool>, "project_key": <string|null>}}`.
- CodeRabbit is present iff the PR's status rollup has a CodeRabbit status check or the PR has any
  comment by the CodeRabbit bot.
- Sonar is present iff the PR's status rollup has a check whose name contains `sonar` (case-insensitive).
- The Sonar project key SHALL be, in order: the config's `reviewers.sonar.project_key`, else the
  `sonar.projectKey` property of `sonar-project.properties` at the repo root, else the `id` query parameter
  of the Sonar check's details URL, else null.
- A `gh` failure SHALL exit 2 with the error on stderr and print no JSON. A missing or non-numeric PR SHALL
  be a usage error (exit 2).

#### Scenario: CodeRabbit by status check
- **WHEN** the PR's rollup has a CodeRabbit status check and the PR has no CodeRabbit comment
- **THEN** the output has `"coderabbit": true`

#### Scenario: CodeRabbit by comment before its status appears
- **WHEN** the rollup has no CodeRabbit check but the PR has a comment by the CodeRabbit bot
- **THEN** the output has `"coderabbit": true`

#### Scenario: No bots
- **WHEN** the rollup has only GitHub Actions checks and the PR has no bot comments
- **THEN** the output is `{"coderabbit": false, "sonar": {"present": false, "project_key": null}}`

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
- **WHEN** `gh` exits non-zero while reading the PR
- **THEN** the command prints no JSON and exits 2

### Requirement: Waiting for reviews needs no configuration
`la-wait-for-reviews` SHALL NOT read the repo configuration and SHALL NOT accept `--skip-coderabbit`. Its
CodeRabbit settle stage SHALL run iff CodeRabbit is present on the PR by the same rule as `la-pr-reviewers`.
The CLI manifest SHALL have no per-command `gate` field.

#### Scenario: CodeRabbit not on the PR
- **WHEN** the PR has no CodeRabbit check and no CodeRabbit comment and the status rollup is clear
- **THEN** `la-wait-for-reviews` skips the CodeRabbit settle and exits 0

#### Scenario: CodeRabbit present by comment only
- **WHEN** the rollup is clear, has no CodeRabbit check, and the PR has a CodeRabbit summary comment newer than the head commit
- **THEN** the settle stage runs and reports the summary as updated

#### Scenario: Old flag rejected
- **WHEN** `la-wait-for-reviews 7 --skip-coderabbit` runs
- **THEN** it exits with the usage-error code
