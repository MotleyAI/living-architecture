# repo-config Specification

## Purpose
Which parts of the flow a repo uses, recorded as explicit decisions in `living-architecture.yaml`, and the
`la-doctor` checks that tell a skill whether the repo is onboarded and whether those decisions match the disk.

## Requirements

### Requirement: The config records each gate as an explicit key
`living-architecture.yaml` SHALL accept, with these defaults:
- `format`: the repo format, a version string (default null; see "Every command checks the declared format")
- `tracker`: one of `linear`, `github` or `none` (default `linear`)
- `openspec`: boolean (default `true`)
- `architecture`: boolean (default `false`)
- `reviewers.codex`: boolean (default `true`)
- `reviewers.sonar.project_key`: string or null (default null)
- `conventions.rules`: a list of conventions rule ids (default: every rule id in the shared conventions
  registry, in registry order)

It SHALL NOT accept `reviewers.coderabbit` or `reviewers.sonar.enabled`. Every key stays optional in the schema;
the format check, not the schema, requires a committed file to declare `format`. `living-architecture.local.yaml`
SHALL NOT accept `format`.

#### Scenario: Defaults of the gate keys
- **WHEN** a repo has no `living-architecture.yaml` and `la-config show` runs
- **THEN** the output has `format: null`, `tracker: linear`, `openspec: true`, `architecture: false`, `reviewers.codex: true`, `reviewers.sonar.project_key: null` and `conventions.rules` listing every registry rule, and the command exits 0

#### Scenario: Declared format shown
- **WHEN** the config declares the current format and `la-config get format` runs
- **THEN** it prints the current format and exits 0

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

#### Scenario: Format in the local file
- **WHEN** `living-architecture.local.yaml` sets `format` and `la-config show` runs
- **THEN** the command exits 1 and its error names `format`

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

### Requirement: Every command checks the declared format
The repo format is the `format` key of the committed `living-architecture.yaml`: the `la` version that introduced
the format, three dot-separated decimal integers without leading zeros (`0.4.0`). The current format SHALL come
from the shared contract. Versions SHALL compare component by component as integers of any size.

Every command the CLI manifest does not mark exempt SHALL check the declared format after parsing its arguments
(so `--help` and usage errors behave as before) and before anything else, reading the committed file with the
shared YAML profile and before its schema is checked:
- without a committed `living-architecture.yaml`, or when it cannot be read, is not valid YAML or is not a mapping,
  the check SHALL pass and the command SHALL behave as it did before this requirement;
- `format` absent SHALL be refused with a message naming the current format and `la-arch-migrate`;
- `format` that is not such a version string (any YAML type) SHALL be refused with a message showing the value
  and the current format;
- `format` newer than the current format SHALL be refused with a message naming the declared format as the `la`
  version to upgrade to;
- `format` older than the current format SHALL be refused with a message naming both formats and `la-arch-migrate`;
- `format` equal to the current format SHALL pass.

A refusal SHALL print its message on stderr and exit 2, with no other output. `living-architecture.local.yaml`
SHALL NOT take part in the check. A command run by the other twin SHALL be checked by that twin.

#### Scenario: Newer format refused by the checker
- **WHEN** the config declares `format: 9.0.0` and `la-arch-check` runs
- **THEN** it exits 2 with the message naming `9.0.0` as the `la` version to upgrade to and prints nothing else

#### Scenario: Newer format refused by the diagrams
- **WHEN** the config declares `format: 9.0.0` and `la-arch-diagrams` runs
- **THEN** it exits 2 with the same message and rewrites no doc

#### Scenario: Newer format refused by la-config
- **WHEN** the config declares `format: 9.0.0` and `la-config get tracker` runs
- **THEN** it exits 2 with the same message

#### Scenario: Newer format with a newer key
- **WHEN** the config declares `format: 9.0.0` and also sets a key this `la` does not know, and `la-config show` runs
- **THEN** it exits 2 with the format message and no schema error

#### Scenario: Very large version components
- **WHEN** the config declares `format: 99999999999999999999.0.0` and `la-arch-check` runs through either twin
- **THEN** it exits 2 with the newer-format message naming `99999999999999999999.0.0`

#### Scenario: Older format refused
- **WHEN** the config declares `format: 0.3.0` and `la-arch-check`, `la-arch-diagrams` or `la-config show` runs
- **THEN** it exits 2 with the message naming `0.3.0`, the current format and `la-arch-migrate`

#### Scenario: Missing format refused
- **WHEN** the committed config has no `format` and `la-arch-check`, `la-arch-diagrams` or `la-config show` runs
- **THEN** it exits 2 with the message naming the current format and `la-arch-migrate`

#### Scenario: Invalid format values
- **WHEN** the config declares `format` as `0.4`, `v0.4.0`, `0.04.0`, null, `true`, a list or a mapping and `la-config show` runs
- **THEN** it exits 2 with the invalid-format message showing the value

#### Scenario: No committed file
- **WHEN** a repo has no `living-architecture.yaml`, with or without `living-architecture.local.yaml`, and `la-config show` runs
- **THEN** it exits 0 with the resolved configuration as before

#### Scenario: Malformed config keeps its existing error
- **WHEN** the committed config is not valid YAML and `la-config show` runs
- **THEN** it exits 1 with the configuration error it reported before this requirement

#### Scenario: Help and usage errors unaffected
- **WHEN** the committed config has no `format` and `la-arch-check --help` or `la-arch-check --bogus` runs
- **THEN** the help is printed with exit 0, or the usage error exits 2 as before, with no format message

#### Scenario: Exempt commands run
- **WHEN** the committed config has no `format` and an exempt review shim runs
- **THEN** it runs as before, with no format message

#### Scenario: Current format passes
- **WHEN** the config declares the current format and `la-arch-check` runs on a clean architecture
- **THEN** it exits 0 as before

### Requirement: la-doctor reports the format check
When the committed `living-architecture.yaml` exists, `la-doctor` SHALL run the format check before the config
checks. A refusal SHALL be printed as its problem line and make it exit 1; the config-dependent checks (schema,
config-against-disk, language executables) SHALL then be skipped, while the version, plugin, local-file and
required-executable checks still run.

#### Scenario: Doctor reports a newer format
- **WHEN** the config declares `format: 9.0.0` and also sets a key this `la` does not know, and `la-doctor` runs
- **THEN** it prints the newer-format problem, no schema error, and exits 1

#### Scenario: Doctor reports an older format
- **WHEN** the config declares `format: 0.3.0` and `la-doctor` runs
- **THEN** it prints the older-format problem naming `la-arch-migrate` and exits 1

#### Scenario: Doctor reports a missing format
- **WHEN** the committed config has no `format` and `la-doctor --require-config` runs
- **THEN** it prints the missing-format problem naming `la-arch-migrate` and exits 1

#### Scenario: Doctor keeps the version check
- **WHEN** the config has no `format` and `la-doctor --expect 0.0.1` runs
- **THEN** it prints both the version-mismatch problem and the missing-format problem and exits 1
