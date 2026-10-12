## ADDED Requirements

### Requirement: A local file overrides the per-person keys
An optional `living-architecture.local.yaml` at the repo root SHALL be deep-merged over `living-architecture.yaml`
(over an empty mapping when that file is absent): mappings merge key by key, any other value replaces. The
merged data SHALL then resolve and validate exactly as the committed file alone does today, and every
command that reads the config SHALL see the merged result.

The local file SHALL accept only `tracker` and `reviewers.codex`, with the same types and values as the
committed file. Any other key SHALL be a config error that names the key and the local file, and exits 1. A
local file that is not valid YAML, or whose top level is not a mapping, SHALL be a config error that names
the local file. An empty or comments-only local file SHALL override nothing. A path that is not a regular
file SHALL count as absent, as for the committed file.

`la-config show` SHALL print the merged configuration on stdout exactly as it prints a configuration today.
For each key the local file sets, in schema order, it SHALL print one note on stderr naming the dotted key
and the local file, even when the local value equals the committed one; it SHALL still exit 0.
`la-config get` SHALL print no such note.

#### Scenario: Local values override the committed file
- **WHEN** the committed file sets `tracker: github` and `reviewers: {codex: true}`, the local file sets `tracker: github` and `reviewers: {codex: false}`, and `la-config show` runs
- **THEN** stdout is the configuration with `tracker: github` and `reviewers.codex: false`, stderr holds exactly two notes naming the local file, first `tracker`, then `reviewers.codex`, and the command exits 0

#### Scenario: Merge keeps sibling keys
- **WHEN** the committed file sets `reviewers: {sonar: {project_key: o_r}}`, the local file sets `reviewers: {codex: false}`, and `la-config show` runs
- **THEN** the output has `reviewers.codex: false` and `reviewers.sonar.project_key: o_r`

#### Scenario: Local file without a committed file
- **WHEN** a repo has only `living-architecture.local.yaml` setting `tracker: none`, and `la-config show` runs
- **THEN** the output has `tracker: none` and every other key at its schema default, and the command exits 0

#### Scenario: Empty local file
- **WHEN** the local file is empty and `la-config show` runs
- **THEN** stdout equals the output without a local file, stderr is empty, and the command exits 0

#### Scenario: Repo decision refused
- **WHEN** the local file sets `openspec: false` and `la-config show` runs
- **THEN** the command exits 1 and its error names `openspec` and `living-architecture.local.yaml`

#### Scenario: Nested key outside the allowlist refused
- **WHEN** the local file sets `reviewers: {sonar: {project_key: o_r}}` and `la-config show` runs
- **THEN** the command exits 1 and its error names `sonar` and `living-architecture.local.yaml`

#### Scenario: Invalid local value
- **WHEN** the local file sets `tracker: jira` and `la-config show` runs
- **THEN** the command exits 1 and its error names `tracker` and `living-architecture.local.yaml`

#### Scenario: Invalid local YAML
- **WHEN** the local file is not valid YAML and `la-config show` runs
- **THEN** the command exits 1 and its error names `living-architecture.local.yaml`

#### Scenario: Local top level not a mapping
- **WHEN** the local file is a YAML list and `la-config show` runs
- **THEN** the command exits 1 and its error names `living-architecture.local.yaml`

#### Scenario: get sees the override without notes
- **WHEN** the local file sets `tracker: none` and `la-config get tracker` runs
- **THEN** it prints `none`, stderr is empty, and it exits 0

#### Scenario: Doctor names the local file as a source
- **WHEN** a repo has a valid, consistent `living-architecture.yaml` and a git-ignored, valid `living-architecture.local.yaml`, and `la-doctor` runs
- **THEN** its ok line names `living-architecture.yaml + living-architecture.local.yaml` as the config source and it exits 0

#### Scenario: Doctor reports an invalid local file without a committed file
- **WHEN** a repo has no `living-architecture.yaml`, its `living-architecture.local.yaml` sets `openspec: false`, and `la-doctor` runs
- **THEN** it reports the config error naming `openspec` and exits 1

### Requirement: la-doctor keeps the local file out of git
When `living-architecture.local.yaml` exists inside a git repository, `la-doctor` SHALL report exactly one of
the following as a finding and exit 1, after the config and consistency findings and before the
missing-executable findings:
- the file is tracked by git, staged-only included (text names `git rm --cached`)
- otherwise, git does not ignore the file (text names `.gitignore`)
- git fails while checking

Outside a git repository, or when the local file does not exist, no such check SHALL run.

#### Scenario: Ignored local file
- **WHEN** `.gitignore` lists `living-architecture.local.yaml`, the file exists, and `la-doctor` runs
- **THEN** it reports no local-file finding

#### Scenario: Tracked local file
- **WHEN** `living-architecture.local.yaml` is committed and `la-doctor` runs
- **THEN** it prints the tracked-local-file finding naming `git rm --cached` and exits 1

#### Scenario: Staged local file
- **WHEN** `living-architecture.local.yaml` is staged but not committed, even though `.gitignore` lists it, and `la-doctor` runs
- **THEN** it prints the tracked-local-file finding and exits 1

#### Scenario: Local file not ignored
- **WHEN** `living-architecture.local.yaml` exists, is untracked, and no ignore rule matches it, and `la-doctor` runs
- **THEN** it prints the not-ignored finding naming `.gitignore` and exits 1

#### Scenario: Git fails while checking
- **WHEN** `living-architecture.local.yaml` exists, git fails inside the repo, and `la-doctor` runs
- **THEN** it prints the local-file git-failure finding and exits 1

#### Scenario: Outside git
- **WHEN** the root has no `.git`, `living-architecture.local.yaml` exists, and `la-doctor` runs
- **THEN** it reports no local-file finding

## MODIFIED Requirements

### Requirement: la-doctor can require the config file
`la-doctor --require-config` SHALL report a missing `living-architecture.yaml` at the repo root as a finding
whose text names `/la:init`, and exit 1. A `living-architecture.local.yaml` alone SHALL NOT count as the
config file. Without `--require-config`, a missing file SHALL keep today's healthy report built on defaults.

#### Scenario: Required and missing
- **WHEN** a repo has no `living-architecture.yaml` and `la-doctor --require-config` runs
- **THEN** it prints the missing-config finding naming `/la:init` and exits 1

#### Scenario: Required and only the local file present
- **WHEN** a repo has a valid, git-ignored `living-architecture.local.yaml` but no `living-architecture.yaml`, and `la-doctor --require-config` runs
- **THEN** it prints the missing-config finding naming `/la:init` and exits 1

#### Scenario: Not required and missing
- **WHEN** a repo has no `living-architecture.yaml` and `la-doctor` runs without `--require-config`
- **THEN** it reports the defaults source and exits 0, exactly as before this change

#### Scenario: Required and present
- **WHEN** a repo has a valid, consistent `living-architecture.yaml` and `la-doctor --require-config` runs
- **THEN** it reports the config file as its source and exits 0

### Requirement: la-doctor checks the config against the disk
When `living-architecture.yaml` exists, `la-doctor` SHALL check the merged configuration (the committed file
with `living-architecture.local.yaml` over it) and report each of the following as its own finding and exit 1:
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

#### Scenario: Local override takes part in the checks
- **WHEN** the committed file sets `openspec: false`, the repo has no `openspec/` directory, the git-ignored local file sets `tracker: none`, and `la-doctor` runs
- **THEN** it prints the no-plan-store finding and exits 1

#### Scenario: Several inconsistencies
- **WHEN** the config sets `openspec: true` and `architecture: true` and neither `openspec/` nor `architecture/index.yaml` exists
- **THEN** `la-doctor` prints both findings in a fixed order and exits 1

#### Scenario: No file, no consistency checks
- **WHEN** a repo has no `living-architecture.yaml` and no `openspec/` directory and `la-doctor` runs
- **THEN** it reports no OpenSpec finding and exits 0
