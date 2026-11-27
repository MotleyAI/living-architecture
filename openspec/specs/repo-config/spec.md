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
- `tracker: none` with `openspec: false`, only under `--require-plan-store`

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
- **WHEN** the config sets `tracker: none` and `openspec: false` and `la-doctor --require-plan-store` runs
- **THEN** it prints the no-plan-store finding and exits 1

#### Scenario: Plan store not required
- **WHEN** the config sets `tracker: none` and `openspec: false` and `la-doctor` runs without `--require-plan-store`
- **THEN** it reports no no-plan-store finding

#### Scenario: Local override takes part in the checks
- **WHEN** the committed file sets `openspec: false`, the repo has no `openspec/` directory, the git-ignored local file sets `tracker: none`, and `la-doctor --require-plan-store` runs
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

#### Scenario: trmv command in an la repo checks the la file
- **WHEN** `living-architecture.yaml` declares `format: 0.4.0` and `trmv-refactor` or `trmv-typecheck` runs
- **THEN** it exits 2 with the older-format message naming `0.4.0`, `0.14.0` and `la-arch-migrate`

#### Scenario: trmv file with a missing format
- **WHEN** `trmv.yaml` has no `format` and `trmv-config show` runs
- **THEN** it exits 2 with the message naming `format: 0.14.0` as the line to add

#### Scenario: trmv file with a newer format
- **WHEN** `trmv.yaml` declares `format: 9.0.0` and `trmv-typecheck` runs
- **THEN** it exits 2 with the message naming `9.0.0` as the `trmv` version to upgrade to

#### Scenario: trmv file with an older or invalid format
- **WHEN** `trmv.yaml` declares `format: 0.11.0`, or `format: v0.14.0`, and `trmv-config show` runs
- **THEN** it exits 2 with the older-format message naming both formats, or the invalid-format message showing the value

#### Scenario: trmv file at the current format
- **WHEN** `trmv.yaml` declares `format: 0.14.0` and `trmv-config get format` runs
- **THEN** it prints `0.14.0` and exits 0

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

#### Scenario: trmv-only repo
- **WHEN** a repo has only `trmv.yaml` setting `commands: {typecheck: {python: 'basedpyright -p app'}}` and `trmv-typecheck` runs
- **THEN** Python is checked with `basedpyright -p app`

#### Scenario: la repo read by trmv
- **WHEN** a repo has only `living-architecture.yaml` setting `commands.typecheck.python` and `trmv-typecheck` runs
- **THEN** Python is checked with that command

#### Scenario: Both files refused by a trmv command
- **WHEN** a repo has both `trmv.yaml` and `living-architecture.yaml` and `trmv-refactor`, `trmv-typecheck` or `trmv-config show` runs
- **THEN** it exits 2 with the message naming both files and prints nothing else

#### Scenario: Both files refused by an la command
- **WHEN** a repo has both files and `la-check-conventions --base main` or `la-config show` runs
- **THEN** it exits 2 with the same message

#### Scenario: la key in the trmv file
- **WHEN** `trmv.yaml` sets `tracker: none` and `trmv-config show` runs
- **THEN** it exits 1 and its error names `tracker` and `trmv.yaml`

#### Scenario: la command ignores the trmv file
- **WHEN** a repo has only `trmv.yaml` and `la-config show` runs
- **THEN** it prints the defaults, exactly as with no config file

#### Scenario: Local file ignored by trmv
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

### Requirement: la-arch-migrate moves the exempt key
`la-arch-migrate` on a `living-architecture.yaml` at format 0.4.0 SHALL, as its 0.4.0-to-0.14.0 step, move
`conventions.exempt` to a top-level `exempt` and then stamp `format: 0.14.0`, editing the text: the entry's lines
(its key line, its value and every comment line inside it) SHALL move verbatim, dedented by the entry's indent, to
directly after the `format` line, and a `conventions` mapping left empty SHALL be removed with its key line. A file
without `conventions.exempt` SHALL only be stamped. Every other byte SHALL be kept. A flow-style `conventions`
mapping, an anchor, alias or tag on the entry or inside its value, or a merge key in `conventions`, SHALL make the
step not migratable (exit 2, nothing written) with a message naming the manual edit. Both twins SHALL produce
byte-identical files and output.

#### Scenario: Block sequence moved
- **WHEN** the file at format 0.4.0 holds `conventions:` with `  text_ratio_max: 0.2` and `  exempt:` followed by `    - 'gen/*'  # generated`, and `la-arch-migrate` runs
- **THEN** the file holds `format: 0.14.0`, then `exempt:` and `  - 'gen/*'  # generated`, and `conventions:` keeps only `text_ratio_max`

#### Scenario: Flow sequence moved and empty mapping removed
- **WHEN** the file at format 0.4.0 holds `conventions:` with only `  exempt: ['conformance/*']   # fixtures`, and `la-arch-migrate` runs
- **THEN** the file holds `exempt: ['conformance/*']   # fixtures` after the `format` line and no `conventions` key

#### Scenario: Nothing to move
- **WHEN** the file at format 0.4.0 has no `conventions.exempt` and `la-arch-migrate` runs
- **THEN** only the `format` line changes, to `format: 0.14.0`

#### Scenario: Flow-style conventions not migratable
- **WHEN** the file at format 0.4.0 holds `conventions: {exempt: [gen/*], rules: []}` and `la-arch-migrate` runs
- **THEN** it exits 2, names the manual edit, and writes nothing

#### Scenario: Aliased entry not migratable
- **WHEN** the file at format 0.4.0 holds `exempt: *globs` under `conventions` and `la-arch-migrate` runs
- **THEN** it exits 2 and writes nothing

#### Scenario: Same result from either twin
- **WHEN** `la-arch-migrate` runs on the same 0.4.0 file through each twin
- **THEN** the written files and stdout are byte-identical

### Requirement: trmv-config prints trmv's resolved config
`trmv-config get <key>` and `trmv-config show` SHALL behave as `la-config`'s subcommands, over the config file trmv reads
and only the trmv keys: `format`, `exempt`, `commands.test`, `commands.typecheck`, `refactor` and their sub-keys, plus
`languages` and `lang.<language>.<key>` exactly as `la-config` defines them. Any other key SHALL exit 2 with the
unknown-key message. `la-config get` SHALL still accept every key, the trmv keys included.

#### Scenario: Show in a trmv-only repo
- **WHEN** a repo has `trmv.yaml` declaring `format: 0.14.0` and `trmv-config show` runs
- **THEN** it prints the resolved `format`, `exempt`, `commands` and `refactor` and exits 0

#### Scenario: la key refused
- **WHEN** `trmv-config get tracker` runs
- **THEN** it exits 2 with the unknown-key message

#### Scenario: Languages through either command
- **WHEN** `trmv-config get languages` and `la-config get languages` run in the same la repo
- **THEN** both print the same list

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
