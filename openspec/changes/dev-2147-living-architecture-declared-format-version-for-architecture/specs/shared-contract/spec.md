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
- **THEN** each exits 2 with the missing-format message, and each exempt command does not print it
