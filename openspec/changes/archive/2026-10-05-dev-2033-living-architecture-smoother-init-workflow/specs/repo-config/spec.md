## Purpose

Which parts of the flow a repo uses, recorded as explicit decisions in `living-architecture.yaml`, and the
`la-doctor` checks that tell a skill whether the repo is onboarded and whether those decisions match the disk.

## ADDED Requirements

### Requirement: The config records each gate as an explicit key
`living-architecture.yaml` SHALL accept, with these defaults:
- `tracker`: one of `linear`, `github` or `none` (default `linear`)
- `openspec`: boolean (default `true`)
- `architecture`: boolean (default `false`)
- `reviewers.codex`: boolean (default `true`)
- `reviewers.sonar.project_key`: string or null (default null)
- `conventions.rules`: a list of conventions rule ids (default: every rule id in the shared conventions
  registry, in registry order)

It SHALL NOT accept `reviewers.coderabbit` or `reviewers.sonar.enabled`. Every key stays optional.

#### Scenario: Defaults of the gate keys
- **WHEN** a repo has no `living-architecture.yaml` and `la-config show` runs
- **THEN** the output has `tracker: linear`, `openspec: true`, `architecture: false`, `reviewers.codex: true`, `reviewers.sonar.project_key: null` and `conventions.rules` listing every registry rule, and the command exits 0

#### Scenario: Removed CodeRabbit key
- **WHEN** the config sets `reviewers: {coderabbit: true}` and `la-config show` runs
- **THEN** the command exits 1 and its error names `coderabbit`

#### Scenario: Removed Sonar switch
- **WHEN** the config sets `reviewers: {sonar: {enabled: true, project_key: o_r}}` and `la-config show` runs
- **THEN** the command exits 1 and its error names `enabled`

#### Scenario: Unknown tracker
- **WHEN** the config sets `tracker: jira` and `la-config show` runs
- **THEN** the command exits 1 and its error names `tracker`

#### Scenario: Unknown conventions rule
- **WHEN** the config sets `conventions: {rules: [import-not-top, no-such-rule]}` and `la-config show` runs
- **THEN** the command exits 1 and its error names `no-such-rule`

### Requirement: la-doctor can require the config file
`la-doctor --require-config` SHALL report a missing `living-architecture.yaml` at the repo root as a finding
whose text names `/la:init`, and exit 1. Without `--require-config`, a missing file SHALL keep today's healthy
report built on defaults.

#### Scenario: Required and missing
- **WHEN** a repo has no `living-architecture.yaml` and `la-doctor --require-config` runs
- **THEN** it prints the missing-config finding naming `/la:init` and exits 1

#### Scenario: Not required and missing
- **WHEN** a repo has no `living-architecture.yaml` and `la-doctor` runs without `--require-config`
- **THEN** it reports the defaults source and exits 0, exactly as before this change

#### Scenario: Required and present
- **WHEN** a repo has a valid, consistent `living-architecture.yaml` and `la-doctor --require-config` runs
- **THEN** it reports the config file as its source and exits 0

### Requirement: la-doctor checks the config against the disk
When `living-architecture.yaml` exists, `la-doctor` SHALL report each of the following as its own finding
and exit 1:
- `openspec: true` without an `openspec/` directory (text names `/la:openspec-init`)
- `openspec: false` with an `openspec/` directory
- `architecture: true` without `architecture/index.yaml` (text names `/la:arch-init`)
- `architecture: false` with `architecture/index.yaml`
- `tracker: none` with `openspec: false`

A directory named `architecture/` without `index.yaml` SHALL NOT count as a living-architecture setup. When
the file does not exist, none of these checks SHALL run.

#### Scenario: OpenSpec enabled but absent
- **WHEN** the config sets `openspec: true`, the repo has no `openspec/` directory, and `la-doctor` runs
- **THEN** it prints the finding naming `/la:openspec-init` and exits 1

#### Scenario: OpenSpec disabled but present
- **WHEN** the config sets `openspec: false`, the repo has an `openspec/` directory, and `la-doctor` runs
- **THEN** it prints the disabled-but-present OpenSpec finding and exits 1

#### Scenario: Architecture enabled but absent
- **WHEN** the config sets `architecture: true`, the repo has no `architecture/index.yaml`, and `la-doctor` runs
- **THEN** it prints the finding naming `/la:arch-init` and exits 1

#### Scenario: Architecture disabled but present
- **WHEN** the config sets `architecture: false`, the repo has `architecture/index.yaml`, and `la-doctor` runs
- **THEN** it prints the disabled-but-present architecture finding and exits 1

#### Scenario: Unrelated architecture directory
- **WHEN** the config sets `architecture: false` and the repo has an `architecture/` directory holding only unrelated documents
- **THEN** `la-doctor` reports no architecture finding

#### Scenario: Nowhere to persist the plan
- **WHEN** the config sets `tracker: none` and `openspec: false` and `la-doctor` runs
- **THEN** it prints the no-plan-store finding and exits 1

#### Scenario: Several inconsistencies
- **WHEN** the config sets `openspec: true` and `architecture: true` and neither `openspec/` nor `architecture/index.yaml` exists
- **THEN** `la-doctor` prints both findings in a fixed order and exits 1

#### Scenario: No file, no consistency checks
- **WHEN** a repo has no `living-architecture.yaml` and no `openspec/` directory and `la-doctor` runs
- **THEN** it reports no OpenSpec finding and exits 0
