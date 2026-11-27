## ADDED Requirements

### Requirement: A stealth config file switches stealth mode on
Inside a git repository, the stealth directories SHALL be `<C>/trmv/` and `<C>/living-architecture/`, where `<C>` is
the absolute git common directory of the working tree a command runs in (every linked worktree of a repository
shares it; a submodule has its own). The stealth config files SHALL be `<C>/trmv/trmv.yaml` and
`<C>/living-architecture/living-architecture.yaml`. A trmv command SHALL read, in this order, the first that exists:
`trmv.yaml` at the repo root, `living-architecture.yaml` at the repo root, `<C>/trmv/trmv.yaml`,
`<C>/living-architecture/living-architecture.yaml`. An la command SHALL read `living-architecture.yaml` at the repo
root, else `<C>/living-architecture/living-architecture.yaml`. When more than one of the four files exists, every
command that reads the config SHALL exit 2 with one shared message naming every file present, before the format
check; the doctors report it instead. Outside a git repository no stealth file SHALL be looked up. A path that is not
a regular file SHALL count as absent.

A command SHALL be in stealth mode iff the config file it reads is a stealth config file. `la-config get stealth` and
`trmv-config get stealth` SHALL print `true` or `false`; no config file can set `stealth` (setting it is a config
error naming the key and the file). `la-config show` and `trmv-config show` SHALL print a note on stderr naming the
stealth file they read.

#### Scenario: Stealth config in a linked worktree
- **WHEN** `<C>/living-architecture/living-architecture.yaml` sets `tracker: none` and `la-config get tracker` runs in a linked worktree of the repository
- **THEN** it prints `none`

#### Scenario: Stealth reported
- **WHEN** the only config file is `<C>/living-architecture/living-architecture.yaml` and `la-config get stealth` runs
- **THEN** it prints `true`

#### Scenario: Committed config is not stealth
- **WHEN** the only config file is `living-architecture.yaml` at the repo root and `trmv-config get stealth` runs
- **THEN** it prints `false`

#### Scenario: trmv reads la's stealth config
- **WHEN** the only config file is `<C>/living-architecture/living-architecture.yaml`, setting `commands.typecheck.python`, and `trmv-typecheck` runs
- **THEN** Python is checked with that command

#### Scenario: trmv-only stealth repo
- **WHEN** the only config file is `<C>/trmv/trmv.yaml` and `trmv-config get stealth` runs
- **THEN** it prints `true`

#### Scenario: Committed and stealth config together
- **WHEN** `living-architecture.yaml` exists at the repo root and in `<C>/living-architecture/`, and `la-config show` or `trmv-refactor` runs
- **THEN** it exits 2 with the shared message naming both files and prints nothing else

#### Scenario: Run from a subdirectory
- **WHEN** a command runs from a nested directory of a stealth repo
- **THEN** it reads the same stealth config as from the repo root

#### Scenario: Submodule has its own stealth directory
- **WHEN** the superproject has a stealth config and a command runs inside a submodule that has none
- **THEN** the command reads no stealth config

#### Scenario: Stealth key refused
- **WHEN** a config file sets `stealth: true` and `la-config show` runs
- **THEN** it reports the config error naming `stealth` and the file

### Requirement: The stealth config file stands in for the committed one
In stealth mode, wherever a requirement names the committed config file, or a config file at the repo root, the
stealth config file the command reads SHALL stand in for it, unless a requirement below says otherwise: the format
check and its refusals, `la-arch-migrate`, `la-doctor --require-config`, `trmv-doctor --require-config`, the schema
check and the doctors' ok-line source. `la-arch-migrate` SHALL migrate and stamp the stealth file in place and print
its absolute path.

#### Scenario: Stealth file at an older format
- **WHEN** `<C>/living-architecture/living-architecture.yaml` declares `format: 0.4.0` and `la-check-conventions --base main` runs
- **THEN** it exits 2 with the older-format refusal naming `la-arch-migrate`

#### Scenario: Required config found in the stealth directory
- **WHEN** a repo has no root config file, has a valid `<C>/living-architecture/living-architecture.yaml`, and `la-doctor --require-config` runs
- **THEN** it reports no missing-config finding and its ok line names the stealth file as the source

#### Scenario: Migrating the stealth file
- **WHEN** `la-arch-migrate` runs in a stealth repo whose stealth file declares `format: 0.4.0`
- **THEN** the stealth file is stamped with the current format and no file in the working tree changes

### Requirement: Stealth configs refuse what cannot stay private
A stealth config SHALL refuse `architecture: true` with a config error naming the key and the file. In stealth mode a
`living-architecture.local.yaml` at the repo root SHALL be a config error naming the file, for every la command.
The la stealth config SHALL accept `leaks.allow`, a list of waivable leak tokens (see the stealth-leaks capability);
a core token in it SHALL be a config error naming the token, and `leaks` in a root config file SHALL be a config error
naming the key and the file.

#### Scenario: Architecture refused in stealth
- **WHEN** `<C>/living-architecture/living-architecture.yaml` sets `architecture: true` and `la-config show` runs
- **THEN** it reports the config error naming `architecture` and the file

#### Scenario: Local file refused in stealth
- **WHEN** a stealth repo has `living-architecture.local.yaml` at the repo root and `la-config get tracker` runs
- **THEN** it reports the config error naming `living-architecture.local.yaml`

#### Scenario: Waivable token allowed
- **WHEN** the la stealth config sets `leaks: {allow: [arc42]}` and `la-config get leaks.allow` runs
- **THEN** it prints the list holding `arc42`

#### Scenario: Core token refused
- **WHEN** the la stealth config sets `leaks: {allow: [living-architecture]}` and `la-config show` runs
- **THEN** it reports the config error naming `living-architecture`

#### Scenario: Leaks key outside stealth
- **WHEN** `living-architecture.yaml` at the repo root sets `leaks: {allow: [arc42]}` and `la-config show` runs
- **THEN** it reports the config error naming `leaks` and the file

### Requirement: OpenSpec and the plan store in stealth
In stealth mode, `openspec: true` SHALL mean the repo's own `openspec/` when the repo tracks a path under `openspec/`
at `HEAD`, and otherwise a private OpenSpec store at `<C>/living-architecture/openspec/`. `la-config get
openspec_store` SHALL print the private store's id, `la-` followed by the first 12 hex digits of the SHA-256 of the
absolute path of `<C>/living-architecture/`, when the private store applies, and an empty line otherwise. In place of
the `openspec: true` without `openspec/` finding, `la-doctor` SHALL report, when the private store applies and either
its directory is missing or the OpenSpec CLI does not list the id among its registered stores, one finding naming
`/la:openspec-init`, and exit 1. In stealth mode, `la-doctor --require-plan-store` SHALL report no no-plan-store
finding for any tracker: with `openspec: false` the plan is kept in `<C>/living-architecture/plans/`.

#### Scenario: Private store applies
- **WHEN** a stealth config sets `openspec: true`, the repo tracks nothing under `openspec/`, and `la-config get openspec_store` runs
- **THEN** it prints the `la-` id derived from the stealth directory's path

#### Scenario: Repo's own OpenSpec
- **WHEN** a stealth config sets `openspec: true`, the repo tracks `openspec/specs/a/spec.md`, and `la-config get openspec_store` runs
- **THEN** it prints an empty line

#### Scenario: Private store missing
- **WHEN** a stealth config sets `openspec: true`, the repo tracks nothing under `openspec/`, `<C>/living-architecture/openspec/` does not exist, and `la-doctor` runs
- **THEN** it prints the finding naming `/la:openspec-init` and exits 1

#### Scenario: Private store registered
- **WHEN** the private store exists and the OpenSpec CLI lists its id, and `la-doctor` runs
- **THEN** it reports no OpenSpec finding

#### Scenario: Plan store in stealth without a tracker
- **WHEN** a stealth config sets `tracker: none` and `openspec: false` and `la-doctor --require-plan-store` runs
- **THEN** it reports no no-plan-store finding
