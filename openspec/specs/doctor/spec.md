# doctor Specification

## Purpose
What `dr-doctor` and `la-doctor` check, across the two packages, so a skill's preflight tells whether the installed
tools, the plugin and the repo config fit together.

## Requirements

### Requirement: dr-doctor checks the dr tools and the config dr reads
`dr-doctor` SHALL be exempt from the format check and SHALL report each problem as a `FAIL:` line and exit 1, or
print one ok line naming the dr version and the config source and exit 0. Its checks, in order:
- with `--plugin DIR`, the dr plugin's version against the dr package (as the shared contract defines for doctors);
- both committed config files present (the shared both-files message), which replaces every check below that reads
  the config;
- the format of the file dr reads, as a problem line; a refusal skips the config-dependent checks;
- with `--require-config`, neither `deterministic-refactor.yaml` nor `living-architecture.yaml` at the repo root, as
  a finding naming `/dr:init`;
- the config dr reads failing its schema;
- `git` missing from `PATH`, and the executables of each repo language.

It SHALL NOT check la keys, the local file, OpenSpec, the architecture setup or `gh`. The ok line's config source
SHALL be the file dr reads, or the defaults.

#### Scenario: Healthy dr-only repo
- **WHEN** a repo has a valid `deterministic-refactor.yaml` at format 0.13.0, `git` is on `PATH`, and `dr-doctor --plugin <dr plugin>/skills/init` runs with matching versions
- **THEN** it prints `ok: dr tools 0.13.0; config from deterministic-refactor.yaml` and exits 0

#### Scenario: dr-doctor in an la repo
- **WHEN** a repo has only a valid `living-architecture.yaml` and `dr-doctor` runs
- **THEN** its ok line names `living-architecture.yaml` as the source and no la-only check runs

#### Scenario: Required and missing
- **WHEN** a repo has no config file and `dr-doctor --require-config` runs
- **THEN** it prints the missing-config finding naming `/dr:init` and exits 1

#### Scenario: Both files present
- **WHEN** a repo has both config files and `dr-doctor` runs
- **THEN** it prints the both-files problem, no schema or format problem, and exits 1

#### Scenario: dr file at a newer format
- **WHEN** `deterministic-refactor.yaml` declares `format: 9.0.0` and `dr-doctor` runs
- **THEN** it prints the newer-format problem naming `dr` and exits 1

#### Scenario: gh is not required
- **WHEN** `gh` is absent from `PATH` and `dr-doctor` runs in a healthy dr-only repo
- **THEN** it exits 0

### Requirement: la-doctor also runs dr's checks and checks the dr installation
`la-doctor` SHALL run its existing checks and, in addition, the both-files check (reported once, replacing every
check that reads the config) and a dr-installation check: the `dr-doctor` first found on `PATH` SHALL report, through
`--twin`, the invoking twin's language, la's version and the dr contract hash of the dr library la runs with. When no
`dr-doctor` is on `PATH`, or its line differs, `la-doctor` SHALL report one finding naming the problem and the
invoking twin's la install command, which installs the dr commands too
(`uv tool install living-architecture==<version> --with-executables-from deterministic-refactor`,
`npm install -g living-architecture@<version> deterministic-refactor@<version>`). `la-doctor --require-config` SHALL
keep requiring `living-architecture.yaml`: a repo with only `deterministic-refactor.yaml` SHALL get the la
missing-config finding.

#### Scenario: Plain la install without the dr commands
- **WHEN** the la tools are installed but no `dr-doctor` is on `PATH`, and `la-doctor` runs
- **THEN** it prints the dr-missing finding with the la install command naming `--with-executables-from deterministic-refactor`, and exits 1

#### Scenario: Other dr version on PATH
- **WHEN** the first `dr-doctor` on `PATH` reports version 0.11.0 while la is 0.13.0
- **THEN** `la-doctor` prints the dr-mismatch finding naming both versions and the install command, and exits 1

#### Scenario: Matching dr on PATH
- **WHEN** the first `dr-doctor` on `PATH` reports the invoking language, la's version and la's dr hash
- **THEN** `la-doctor` reports no dr finding

#### Scenario: Both files reported once
- **WHEN** a repo has both config files and `la-doctor` runs
- **THEN** it prints the both-files problem once, no schema, format or consistency problem, and exits 1

#### Scenario: dr-only repo under la-doctor
- **WHEN** a repo has only `deterministic-refactor.yaml` and `la-doctor --require-config` runs
- **THEN** it prints the missing-config finding naming `/la:init` and exits 1

### Requirement: Each doctor prints its own package's ok line
The ok line SHALL name the doctor's package: `ok: dr tools <version>; config from <source>` for `dr-doctor` and
`ok: la tools <version>; config from <source>` for `la-doctor`, with the source rendered as today.

#### Scenario: la ok line unchanged
- **WHEN** a healthy la repo runs `la-doctor` with a matching dr on `PATH`
- **THEN** its ok line equals today's
