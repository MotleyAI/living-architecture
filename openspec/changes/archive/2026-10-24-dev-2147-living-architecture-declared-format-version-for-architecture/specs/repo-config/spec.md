## MODIFIED Requirements

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

## ADDED Requirements

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
