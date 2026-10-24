## MODIFIED Requirements

### Requirement: Command surfaces come from the shared CLI manifest
The set of `la-*` and `dr-*` commands, and each command's subcommands, options, types, choices, repeatability,
required options and positionals, SHALL be defined by the shared CLI manifest. Each installed command SHALL
build its parser from it. Parsing SHALL accept no abbreviated long options and SHALL honour `--`. A usage
error SHALL exit 2. A command declared `passthrough` SHALL hand its raw arguments to its handler. Options the
manifest marks internal SHALL be accepted but omitted from help. The manifest SHALL declare, for each
language-specific command, the languages whose twin implements it natively; a command declaring none is
neutral. The manifest SHALL mark the commands exempt from the format check (`la-arch-migrate`, `la-doctor` and the
review shims); every other command SHALL run the format check, and a format refusal SHALL exit 2 in every command.
Each package's installed entry points SHALL be exactly the manifest's command set, and every command a
skill references SHALL be in the manifest.

#### Scenario: Entry points match the manifest
- **WHEN** either twin's test suite runs
- **THEN** it fails if that package's installed commands (console scripts or `bin` entries) differ from the manifest's commands in either direction

#### Scenario: Abbreviated option rejected
- **WHEN** `la-check-conventions --bas main` runs through either twin
- **THEN** it exits 2 as a usage error

#### Scenario: Accepted invocation vector
- **WHEN** `la-check-conventions --file a.py --file b.py --exclude 'gen/*'` runs
- **THEN** both files are checked, `gen/*` is exempt, and the exit code and stdout equal the golden

#### Scenario: Internal option hidden
- **WHEN** `la-doctor --help` runs
- **THEN** the help text does not mention `--twin`, and `la-doctor --twin` is still accepted

#### Scenario: Skill references only real commands
- **WHEN** a SKILL.md mentions an `la-*` or `dr-*` command absent from the manifest
- **THEN** the skills test fails naming the command

#### Scenario: Every non-exempt command runs the format check
- **WHEN** either twin's test suite runs each manifest command not marked exempt in a repo whose config declares no `format`
- **THEN** each exits 2 with the missing-format message, and no exempt command is refused by it (`la-doctor` reports
  the missing format as one of its problems instead)

### Requirement: YAML is read with one fixed profile
Every YAML input SHALL be read as YAML 1.1, exactly as PyYAML's safe loader reads it: `yes`/`no`/`on`/`off`
are booleans, and a duplicate mapping key takes the last value. A scalar the safe loader cannot construct (an
impossible date such as `2024-13-01`, or `!!int`/`!!float` content that is not a number) SHALL be a YAML error,
reported like any other invalid YAML, never a crash.

#### Scenario: YAML 1.1 boolean
- **WHEN** the config sets `reviewers: {codex: no}`
- **THEN** the resolved `reviewers.codex` is `false`

#### Scenario: Duplicate key
- **WHEN** a mapping in the config repeats a key
- **THEN** the last occurrence wins and no error is raised

#### Scenario: Unconstructible scalar
- **WHEN** the config holds `2024-13-01` as a plain scalar
- **THEN** every command that reads it reports invalid YAML in the config and exits as for any other YAML error
