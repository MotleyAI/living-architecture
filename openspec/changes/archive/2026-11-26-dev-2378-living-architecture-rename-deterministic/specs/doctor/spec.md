## RENAMED Requirements

- FROM: `### Requirement: dr-doctor checks the dr tools and the config dr reads`
- TO: `### Requirement: trmv-doctor checks the trmv tools and the config trmv reads`

- FROM: `### Requirement: la-doctor also runs dr's checks and checks the dr installation`
- TO: `### Requirement: la-doctor also runs trmv's checks and checks the trmv installation`

## MODIFIED Requirements

### Requirement: trmv-doctor checks the trmv tools and the config trmv reads
`trmv-doctor` SHALL be exempt from the format check and SHALL report each problem as a `FAIL:` line and exit 1, or
print one ok line naming the trmv version and the config source and exit 0. Its checks, in order:
- with `--plugin DIR`, the trmv plugin's version against the trmv package (as the shared contract defines for doctors);
- both committed config files present (the shared both-files message), which replaces every check below that reads
  the config;
- the format of the file trmv reads, as a problem line; a refusal skips the config-dependent checks;
- with `--require-config`, neither `trmv.yaml` nor `living-architecture.yaml` at the repo root, as
  a finding naming `/trmv:init`;
- the config trmv reads failing its schema;
- `git` missing from `PATH`, and the executables of each repo language.

It SHALL NOT check la keys, the local file, OpenSpec, the architecture setup or `gh`. The ok line's config source
SHALL be the file trmv reads, or the defaults.

#### Scenario: Healthy dr-only repo
- **WHEN** a repo has a valid `trmv.yaml` at format 0.14.0, `git` is on `PATH`, and `trmv-doctor --plugin <trmv plugin>/skills/init` runs with matching versions
- **THEN** it prints `ok: trmv tools 0.14.0; config from trmv.yaml` and exits 0

#### Scenario: dr-doctor in an la repo
- **WHEN** a repo has only a valid `living-architecture.yaml` and `trmv-doctor` runs
- **THEN** its ok line names `living-architecture.yaml` as the source and no la-only check runs

#### Scenario: Required and missing
- **WHEN** a repo has no config file and `trmv-doctor --require-config` runs
- **THEN** it prints the missing-config finding naming `/trmv:init` and exits 1

#### Scenario: Both files present
- **WHEN** a repo has both config files and `trmv-doctor` runs
- **THEN** it prints the both-files problem, no schema or format problem, and exits 1

#### Scenario: dr file at a newer format
- **WHEN** `trmv.yaml` declares `format: 9.0.0` and `trmv-doctor` runs
- **THEN** it prints the newer-format problem naming `trmv` and exits 1

#### Scenario: gh is not required
- **WHEN** `gh` is absent from `PATH` and `trmv-doctor` runs in a healthy trmv-only repo
- **THEN** it exits 0

### Requirement: la-doctor also runs trmv's checks and checks the trmv installation
`la-doctor` SHALL run its existing checks and, in addition, the both-files check (reported once, replacing every
check that reads the config) and a trmv-installation check: the `trmv-doctor` first found on `PATH` SHALL report, through
`--twin`, the invoking twin's language, la's version and the trmv contract hash of the trmv library la runs with. When no
`trmv-doctor` is on `PATH`, or its line differs, `la-doctor` SHALL report one finding naming the problem and the
invoking twin's la install command, which installs the trmv commands too
(`uv tool install living-architecture==<version> --with-executables-from type-rename-move`,
`npm install -g living-architecture@<version> type-rename-move@<version>`). `la-doctor --require-config` SHALL
keep requiring `living-architecture.yaml`: a repo with only `trmv.yaml` SHALL get the la
missing-config finding.

#### Scenario: Plain la install without the dr commands
- **WHEN** the la tools are installed but no `trmv-doctor` is on `PATH`, and `la-doctor` runs
- **THEN** it prints the trmv-missing finding with the la install command naming `--with-executables-from type-rename-move`, and exits 1

#### Scenario: Other dr version on PATH
- **WHEN** the first `trmv-doctor` on `PATH` reports version 0.11.0 while la is 0.13.0
- **THEN** `la-doctor` prints the trmv-mismatch finding naming both versions and the install command, and exits 1

#### Scenario: Matching dr on PATH
- **WHEN** the first `trmv-doctor` on `PATH` reports the invoking language, la's version and la's trmv hash
- **THEN** `la-doctor` reports no trmv finding

#### Scenario: Both files reported once
- **WHEN** a repo has both config files and `la-doctor` runs
- **THEN** it prints the both-files problem once, no schema, format or consistency problem, and exits 1

#### Scenario: dr-only repo under la-doctor
- **WHEN** a repo has only `trmv.yaml` and `la-doctor --require-config` runs
- **THEN** it prints the missing-config finding naming `/la:init` and exits 1

### Requirement: Each doctor prints its own package's ok line
The ok line SHALL name the doctor's package: `ok: trmv tools <version>; config from <source>` for `trmv-doctor` and
`ok: la tools <version>; config from <source>` for `la-doctor`, with the source rendered as today.

#### Scenario: la ok line unchanged
- **WHEN** a healthy la repo runs `la-doctor` with a matching trmv on `PATH`
- **THEN** its ok line equals today's
