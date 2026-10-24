## ADDED Requirements

### Requirement: la-arch-migrate converts the retired arc42 key format
The arc42 conversion is a step of `la-arch-migrate` (see "la-arch-migrate converts the repo to the current format")
and runs only for a repo whose `living-architecture.yaml` declares no `format`, after the layout conversion, on the
canonical model or the one the layout conversion stages; it converts nothing when `architecture/` holds no LikeC4
source file. It SHALL:
- for each element setting `arc42 '<p>'`, in model order, stage the move of `<p>` to
  `architecture/<element id>.arc42.md` (no move when they are equal), the removal of the `arc42` statement, and the
  removal of the element's `metadata` block when it is then empty; a removed statement or block takes its whole
  lines when nothing but whitespace and a comment shares them, else only itself and the whitespace before it (after
  it when it starts its line);
- for each `cross_cutting_arc42` entry `<p>` in `architecture/index.yaml` that is not `architecture/<name>.arc42.md`
  with no `/` in `<name>`, stage the move of `<p>` to `architecture/<basename of p>` and the rewrite of the entry;
- stage the rename of every `diagrams` key equal to a moved source to its target;
- keep every other byte of `architecture/model.c4` and `architecture/index.yaml` unchanged;
- exit 2 writing nothing, naming the paths, when a source does not exist in the repo, a source is moved more than
  once, two sources share a target, or a target already exists as a file or as a `diagrams` key, a `<p>` already at
  its target counting as a source moved there for the first three; only the first refusal is reported, moves checked in plan order (element docs in model order, then `cross_cutting_arc42` entries
  in file order) and, per move, in that check order;
- before writing, verify that the staged result parses to the same model as the input apart from the removed `arc42`
  keys and emptied `metadata` blocks (elements with metadata, kinds, virtual flags and metadata problems, and
  relations with their legacy flags, in order; findings and metadata findings as multisets), to the same views, and
  to an `index.yaml` equal to the input with the staged entry and key renames; on any difference exit 2 writing
  nothing.

A directory that a cross-cutting move leaves empty SHALL be kept.

#### Scenario: Unversioned canonical repo with arc42 keys
- **WHEN** an unversioned canonical repo's node `python.api` sets `arc42 'architecture/api.arc42.md'` and `index.yaml` maps `architecture/api.arc42.md: [api]` under `diagrams`
- **THEN** the doc is moved byte-identically to `architecture/python.api.arc42.md`, the `arc42` line is gone, the `diagrams` key is renamed, every other byte of `model.c4` and `index.yaml` is unchanged, the format is stamped, and the command exits 0

#### Scenario: Doc already at its target
- **WHEN** a node `python.api` sets `arc42 'architecture/python.api.arc42.md'`
- **THEN** only the `arc42` line is removed and no doc moves

#### Scenario: Emptied metadata block removed
- **WHEN** a virtual node's metadata holds only an `arc42` key
- **THEN** its whole `metadata` block is removed

#### Scenario: Cross-cutting doc flattened
- **WHEN** `cross_cutting_arc42` lists `architecture/security/rules.arc42.md`
- **THEN** the doc moves to `architecture/rules.arc42.md` and the entry is rewritten to it

#### Scenario: Legacy layout and arc42 keys in one run
- **WHEN** an unversioned legacy-layout repo's model sets an `arc42` key
- **THEN** one run writes `architecture/model.c4` without the key, moves the doc, stamps the format, and `la-arch-check` reports no arc42-exists finding for it

#### Scenario: Current-format repo is not converted
- **WHEN** the config declares the current format and an element still sets `arc42`
- **THEN** `la-arch-migrate` prints that there is nothing to migrate, and `la-arch-check` exits 2 with the retired-key error

#### Scenario: Missing source refused
- **WHEN** a node sets `arc42 'architecture/gone.arc42.md'` and that file does not exist
- **THEN** `la-arch-migrate` exits 2 naming `architecture/gone.arc42.md`, the config is not stamped and the repo is unchanged

#### Scenario: Source outside the repo refused
- **WHEN** a node sets `arc42 '/etc/hosts'`
- **THEN** `la-arch-migrate` exits 2 naming `/etc/hosts` as not existing and the repo is unchanged

#### Scenario: Target taken refused
- **WHEN** a node `python.api` sets `arc42 'architecture/api.arc42.md'` and `architecture/python.api.arc42.md` also exists
- **THEN** `la-arch-migrate` exits 2 naming the target and the repo is unchanged

#### Scenario: Diagrams key taken refused
- **WHEN** a doc moves to `architecture/python.api.arc42.md` and `diagrams` already has that key
- **THEN** `la-arch-migrate` exits 2 naming the key and the repo is unchanged

#### Scenario: Shared target refused
- **WHEN** `cross_cutting_arc42` lists `architecture/a/rules.arc42.md` and `architecture/b/rules.arc42.md`
- **THEN** `la-arch-migrate` exits 2 naming `architecture/rules.arc42.md` and the repo is unchanged

#### Scenario: Source moved twice refused
- **WHEN** two nodes set `arc42` to the same path
- **THEN** `la-arch-migrate` exits 2 naming that path and the repo is unchanged

#### Scenario: Statement sharing its line
- **WHEN** a node's metadata reads `metadata { package 'pkg.api' arc42 'architecture/api.arc42.md' }` on one line
- **THEN** that line becomes `metadata { package 'pkg.api' }`, the doc moves, and every other byte is unchanged

#### Scenario: Doc already at its target claimed by another element
- **WHEN** node `python.api` sets `arc42 'architecture/python.api.arc42.md'` and node `python.core` sets the same path
- **THEN** `la-arch-migrate` exits 2 naming that path and the repo is unchanged

#### Scenario: Doc already at its target missing
- **WHEN** node `python.api` sets `arc42 'architecture/python.api.arc42.md'` and that file does not exist
- **THEN** `la-arch-migrate` exits 2 naming it and the repo is unchanged

## MODIFIED Requirements

### Requirement: la-arch-migrate converts the repo to the current format
`la-arch-migrate [--root DIR]` SHALL read the committed `living-architecture.yaml` as YAML only (its schema is not
checked) and:
- without a committed `living-architecture.yaml`, exit 2 with a message naming `/la:init`, writing nothing;
- when the file cannot be read, is not valid YAML or is not a mapping, exit 2, writing nothing;
- when `format` is invalid or newer than the current format, exit 2 with the format check's message, writing
  nothing;
- when `format` equals the current format, print that there is nothing to migrate, naming the format, change
  nothing and exit 0;
- when `format` is older than the current format and no conversion from it exists, exit 2 naming the declared
  format, writing nothing;
- when `format` is absent, run the layout conversion (see "la-arch-migrate converts the legacy layout"), then the
  arc42 conversion (see "la-arch-migrate converts the retired arc42 key format"), then stamp the current format.

Stamping SHALL insert one `format: <current>` line, keeping every other byte of the file: after the leading comment
lines, blank lines, `%` directive lines and a `---` document marker, before the first other line, or at the end of a
file that has no other line (adding a missing final line break first). The inserted line SHALL use the file's line
break (CRLF when the file's first line break is CRLF, else LF). Before writing, the stamped text SHALL be verified to
parse to the original mapping plus `format` with the current format; otherwise `la-arch-migrate` SHALL exit 2 with a
message saying the format must be added by hand, writing nothing.

The run SHALL be all-or-nothing across the layout files, `architecture/index.yaml`, the moved docs and the config:
the config SHALL be replaced atomically as the last change; on a filesystem error every created file SHALL be
removed, every moved doc moved back, and every deleted or replaced file and the `architecture/model/` directory
restored byte-for-byte, and the command SHALL exit 2. When restoring fails, the message SHALL name every path left
changed. On success it SHALL print each written path (`architecture/model.c4`, `architecture/views.c4` and
`architecture/index.yaml`, each only when written, then `living-architecture.yaml`), then each moved doc, then each
deleted path, one per line, and exit 0.

#### Scenario: No config file
- **WHEN** a repo has no committed `living-architecture.yaml` and `la-arch-migrate` runs
- **THEN** it exits 2 with a message naming `/la:init` and the repo is unchanged

#### Scenario: Already current
- **WHEN** the config declares the current format and `la-arch-migrate` runs
- **THEN** it prints that there is nothing to migrate, naming the current format, changes nothing and exits 0

#### Scenario: Newer format refused
- **WHEN** the config declares `format: 9.0.0` and `la-arch-migrate` runs
- **THEN** it exits 2 with the message naming `9.0.0` as the `la` version to upgrade to and the repo is unchanged

#### Scenario: Invalid format refused
- **WHEN** the config declares `format: 0.4` and `la-arch-migrate` runs
- **THEN** it exits 2 with the invalid-format message and the repo is unchanged

#### Scenario: Unknown older format refused
- **WHEN** the config declares `format: 0.3.0` and `la-arch-migrate` runs
- **THEN** it exits 2 naming `0.3.0` as a format it cannot migrate from and the repo is unchanged

#### Scenario: Malformed config refused
- **WHEN** the committed config is not valid YAML, or its top level is a scalar or a list, and `la-arch-migrate` runs
- **THEN** it exits 2 and every file is byte-identical to before

#### Scenario: Schema errors do not block stamping
- **WHEN** an unversioned config also sets a removed key such as `reviewers: {coderabbit: true}` and `la-arch-migrate` runs
- **THEN** it stamps the format, keeps the removed key and exits 0

#### Scenario: Stamp after leading comments
- **WHEN** an unversioned config opens with two comment lines and a blank line before `tracker: linear`
- **THEN** the stamped file holds those lines unchanged, then `format: <current>`, then `tracker: linear` and every following byte unchanged

#### Scenario: Stamp after a document marker
- **WHEN** an unversioned config opens with `%YAML 1.1` and `---` before its keys
- **THEN** `format: <current>` is inserted directly after the `---` line

#### Scenario: Stamp keeps CRLF line breaks
- **WHEN** an unversioned config uses CRLF line breaks
- **THEN** the inserted line ends with CRLF and every other byte is unchanged

#### Scenario: Stamp into an empty or comment-only file
- **WHEN** the unversioned config is empty, or holds only comments without a final line break
- **THEN** `format: <current>` is the file's last line and the prior content is unchanged apart from an added final line break

#### Scenario: Unstampable config
- **WHEN** the unversioned config is a flow-style mapping `{tracker: linear}`
- **THEN** `la-arch-migrate` exits 2 saying the format must be added by hand and the repo is unchanged

#### Scenario: Stamped repo passes the format check
- **WHEN** an unversioned repo is migrated and then `la-config show` runs
- **THEN** it exits 0 and prints the current format

#### Scenario: Write failure rolls back the config too
- **WHEN** writing, deleting or replacing the config fails part-way through `la-arch-migrate`
- **THEN** it exits 2 and every legacy file, the `architecture/model/` directory, any pre-existing `model.c4` and `views.c4`, `architecture/index.yaml`, every arc42 doc and `living-architecture.yaml` are byte-identical at their original locations

#### Scenario: Failed rollback named
- **WHEN** a write fails and restoring one of the changed paths also fails
- **THEN** `la-arch-migrate` exits 2 and its message names that path as left changed
