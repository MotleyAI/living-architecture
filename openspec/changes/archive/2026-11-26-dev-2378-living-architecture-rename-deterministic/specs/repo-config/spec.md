## RENAMED Requirements

- FROM: `### Requirement: dr-config prints dr's resolved config`
- TO: `### Requirement: trmv-config prints trmv's resolved config`

## MODIFIED Requirements

### Requirement: Every command checks the declared format
The repo format is the `format` key of the committed config file a command reads (see "Each package reads one
committed config file"): the version of the release that introduced the format, three dot-separated decimal
integers without leading zeros (`0.4.0`). The trmv contract SHALL list, per config file name, its released formats,
every format a release introduced for that file, as a non-empty list of such versions in strictly ascending order;
the file's current format SHALL be its last entry. `living-architecture.yaml` SHALL have the series
`[0.4.0, 0.14.0]` and `trmv.yaml` the series `[0.14.0]`. Versions SHALL compare component by
component as integers of any size.

Every command the CLI manifest does not mark exempt SHALL check the declared format of the file it reads, against
that file's series, after parsing its arguments (so `--help` and usage errors behave as before) and before anything
else, reading the committed file with the shared YAML profile and before its schema is checked:
- without a committed config file, or when it cannot be read, is not valid YAML or is not a mapping, the check SHALL
  pass and the command SHALL behave as it did before this requirement;
- `format` absent SHALL be refused with a message naming the file's current format and, for
  `living-architecture.yaml`, `la-arch-migrate`, or, for `trmv.yaml`, `format: <current>` as the
  line to add;
- `format` that is not such a version string (any YAML type) SHALL be refused with a message showing the value
  and the current format;
- `format` newer than the current format SHALL be refused with a message naming the declared format as the version
  of the file's package (`la` or `trmv`) to upgrade to;
- `format` older than the current format SHALL be refused with a message naming both formats and, for
  `living-architecture.yaml`, `la-arch-migrate`;
- `format` equal to the current format SHALL pass.

A refusal SHALL print its message on stderr and exit 2, with no other output. `living-architecture.local.yaml`
SHALL NOT take part in the check. A command SHALL run the check once, in the twin it was invoked through, before it
forwards anything.

#### Scenario: Released formats well-formed
- **WHEN** either twin of either package reads the released formats from the trmv contract snapshot
- **THEN** each file's list is non-empty, every entry is a version, the entries ascend strictly, and each file's current format is no newer than any package version or `plugin.json` version

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

#### Scenario: dr command in an la repo checks the la file
- **WHEN** `living-architecture.yaml` declares `format: 0.4.0` and `trmv-refactor` or `trmv-typecheck` runs
- **THEN** it exits 2 with the older-format message naming `0.4.0`, `0.14.0` and `la-arch-migrate`

#### Scenario: dr file with a missing format
- **WHEN** `trmv.yaml` has no `format` and `trmv-config show` runs
- **THEN** it exits 2 with the message naming `format: 0.14.0` as the line to add

#### Scenario: dr file with a newer format
- **WHEN** `trmv.yaml` declares `format: 9.0.0` and `trmv-typecheck` runs
- **THEN** it exits 2 with the message naming `9.0.0` as the `trmv` version to upgrade to

#### Scenario: dr file with an older or invalid format
- **WHEN** `trmv.yaml` declares `format: 0.11.0`, or `format: v0.14.0`, and `trmv-config show` runs
- **THEN** it exits 2 with the older-format message naming both formats, or the invalid-format message showing the value

#### Scenario: dr file at the current format
- **WHEN** `trmv.yaml` declares `format: 0.14.0` and `trmv-config get format` runs
- **THEN** it prints `0.14.0` and exits 0

### Requirement: Each package reads one committed config file
The trmv contract SHALL list the committed config file names in order: `trmv.yaml`, then
`living-architecture.yaml`. A trmv command (`trmv-*`, and `la-typecheck`) SHALL read `trmv.yaml` when
it exists at the repo root, else `living-architecture.yaml`. An la command SHALL read `living-architecture.yaml`
only. When both files exist at the repo root, every command that reads the config SHALL exit 2 (`la-config` and
`trmv-config` included) with one shared message naming both files, before the format check; the doctors report it
instead (see the doctor capability). A path that is not a regular file SHALL count as absent. trmv SHALL ignore
`living-architecture.local.yaml`; it overrides only la keys. `trmv.yaml` SHALL accept exactly the
trmv keys: `format`, `exempt`, `commands.test`, `commands.typecheck` and `refactor`, with the same types and defaults
as in `living-architecture.yaml`; any other key SHALL be a config error naming the key and the file.

#### Scenario: dr-only repo
- **WHEN** a repo has only `trmv.yaml` setting `commands: {typecheck: {python: 'basedpyright -p app'}}` and `trmv-typecheck` runs
- **THEN** Python is checked with `basedpyright -p app`

#### Scenario: la repo read by dr
- **WHEN** a repo has only `living-architecture.yaml` setting `commands.typecheck.python` and `trmv-typecheck` runs
- **THEN** Python is checked with that command

#### Scenario: Both files refused by a dr command
- **WHEN** a repo has both `trmv.yaml` and `living-architecture.yaml` and `trmv-refactor`, `trmv-typecheck` or `trmv-config show` runs
- **THEN** it exits 2 with the message naming both files and prints nothing else

#### Scenario: Both files refused by an la command
- **WHEN** a repo has both files and `la-check-conventions --base main` or `la-config show` runs
- **THEN** it exits 2 with the same message

#### Scenario: la key in the dr file
- **WHEN** `trmv.yaml` sets `tracker: none` and `trmv-config show` runs
- **THEN** it exits 1 and its error names `tracker` and `trmv.yaml`

#### Scenario: la command ignores the dr file
- **WHEN** a repo has only `trmv.yaml` and `la-config show` runs
- **THEN** it prints the defaults, exactly as with no config file

#### Scenario: Local file ignored by dr
- **WHEN** `living-architecture.local.yaml` sets `tracker: none` and `trmv-config show` runs in a repo with `living-architecture.yaml`
- **THEN** stdout holds only trmv keys and stderr is empty

### Requirement: Paths outside the repo's own source are one top-level key
The top-level `exempt` key, defined by the trmv schema and embedded in the la schema, SHALL be a list of glob
patterns (the shared glob dialect, repo-relative), default `[]`, naming paths that are not the repo's own source,
such as fixtures and generated code. Repo-language detection SHALL leave out the files it matches, and the
conventions gate SHALL exempt them from every check. `conventions.exempt` SHALL NOT be accepted (a config error
naming `exempt`).

#### Scenario: Default
- **WHEN** a repo has no config file and `trmv-config get exempt` or `la-config get exempt` runs
- **THEN** it prints `[]`

#### Scenario: Retired nested key
- **WHEN** `living-architecture.yaml` at format 0.14.0 sets `conventions: {exempt: ['gen/*']}` and `la-config show` runs
- **THEN** it exits 1 and its error names `exempt`

#### Scenario: Exempt files do not make a language
- **WHEN** a repo with `pyproject.toml` and `tsconfig.json` has `.ts` files only under `fixtures/`, sets `exempt: ['fixtures/**']`, and `trmv-config get languages` runs
- **THEN** it prints `["python"]`

### Requirement: trmv-config prints trmv's resolved config
`trmv-config get <key>` and `trmv-config show` SHALL behave as `la-config`'s subcommands, over the config file trmv reads
and only the trmv keys: `format`, `exempt`, `commands.test`, `commands.typecheck`, `refactor` and their sub-keys, plus
`languages` and `lang.<language>.<key>` exactly as `la-config` defines them. Any other key SHALL exit 2 with the
unknown-key message. `la-config get` SHALL still accept every key, the trmv keys included.

#### Scenario: Show in a dr-only repo
- **WHEN** a repo has `trmv.yaml` declaring `format: 0.14.0` and `trmv-config show` runs
- **THEN** it prints the resolved `format`, `exempt`, `commands` and `refactor` and exits 0

#### Scenario: la key refused
- **WHEN** `trmv-config get tracker` runs
- **THEN** it exits 2 with the unknown-key message

#### Scenario: Languages through either command
- **WHEN** `trmv-config get languages` and `la-config get languages` run in the same la repo
- **THEN** both print the same list
