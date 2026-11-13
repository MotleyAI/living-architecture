# c4-layout Specification

## Purpose
Pin where the LikeC4 model and views live — exactly `architecture/model.c4` and `architecture/views.c4` — so every
reader, ours and the LikeC4 CLI's, sees the same single model, and convert repos from the legacy multi-file layout.

## Requirements

### Requirement: The model and views live in two canonical files
`architecture/` SHALL hold exactly two LikeC4 source files: `architecture/model.c4` and `architecture/views.c4`.
A LikeC4 source file is a file whose name ends, case-sensitively, in one of the extensions listed in the shared
contract (`.c4`, `.likec4`). The following SHALL each be a layout violation:
- a canonical file that does not exist, or whose path exists but is not a regular file (or a symlink to one);
- any other LikeC4 source file under `architecture/`, at any depth; symlinks to files count as files, symlinked
  directories are not descended into;
- a LikeC4 source file under `architecture/` whose bytes are not valid UTF-8; this is the only
  violation reported for that file.

#### Scenario: Canonical layout
- **WHEN** `architecture/` holds `model.c4`, `views.c4`, `index.yaml` and arc42 docs only
- **THEN** there is no layout violation

#### Scenario: Missing model file
- **WHEN** `architecture/model.c4` does not exist
- **THEN** the layout violation names `architecture/model.c4` as missing

#### Scenario: Missing views file
- **WHEN** `architecture/views.c4` does not exist
- **THEN** the layout violation names `architecture/views.c4` as missing

#### Scenario: Canonical path is a directory
- **WHEN** `architecture/model.c4` is a directory
- **THEN** the layout violation names `architecture/model.c4` as not a file

#### Scenario: Stray model file
- **WHEN** `architecture/extra.c4` exists beside the canonical files
- **THEN** the layout violation names `architecture/extra.c4` as stray

#### Scenario: Stray likec4 file
- **WHEN** `architecture/extra.likec4` exists beside the canonical files
- **THEN** the layout violation names `architecture/extra.likec4` as stray

#### Scenario: Nested stray file
- **WHEN** `architecture/sub/deep/x.c4` exists beside the canonical files
- **THEN** the layout violation names `architecture/sub/deep/x.c4` as stray

#### Scenario: Extension match is case-sensitive
- **WHEN** `architecture/notes.C4` exists beside the canonical files
- **THEN** there is no layout violation

#### Scenario: Symlinked stray file
- **WHEN** `architecture/link.c4` is a symlink to a file
- **THEN** the layout violation names `architecture/link.c4` as stray

#### Scenario: Source that is not UTF-8
- **WHEN** `architecture/model.c4` holds bytes that are not valid UTF-8
- **THEN** the layout violation names `architecture/model.c4` as not valid UTF-8 and nothing else about it

### Requirement: Each canonical file holds only its blocks
At top level, ignoring comments and whitespace, `architecture/model.c4` SHALL consist of exactly one
`specification { }` block and exactly one `model { }` block, in either order, and `architecture/views.c4` SHALL
consist of exactly one `views { }` block. Braces inside single-quoted strings and comments SHALL NOT count. Each
of the following SHALL be a layout violation naming the file: a missing required block, a second block of a
kind, a block of a kind not allowed in that file, any other top-level text, and unbalanced or unclosed braces.

#### Scenario: Views block in the model file
- **WHEN** `architecture/model.c4` holds a `views { }` block besides its `specification` and `model` blocks
- **THEN** the layout violation names `architecture/model.c4` and the `views` block

#### Scenario: Model block in the views file
- **WHEN** `architecture/views.c4` holds a `model { }` block after its `views` block
- **THEN** the layout violation names `architecture/views.c4` and the `model` block

#### Scenario: Two model blocks
- **WHEN** `architecture/model.c4` holds two `model { }` blocks
- **THEN** the layout violation names `architecture/model.c4` and the duplicate `model` block

#### Scenario: Missing specification block
- **WHEN** `architecture/model.c4` holds a `model { }` block and no `specification { }` block
- **THEN** the layout violation names `architecture/model.c4` and the missing `specification` block

#### Scenario: Views file without a views block
- **WHEN** `architecture/views.c4` holds only comments
- **THEN** the layout violation names `architecture/views.c4` and the missing `views` block

#### Scenario: Unexpected top-level text
- **WHEN** `architecture/model.c4` holds the line `element foo` outside every block
- **THEN** the layout violation names `architecture/model.c4` and the unexpected top-level text

#### Scenario: Unclosed block
- **WHEN** the `model {` block of `architecture/model.c4` is never closed
- **THEN** the layout violation names `architecture/model.c4` and the unbalanced braces

#### Scenario: Braces in strings and comments
- **WHEN** an element title is `'a { b'` and a comment holds `}`
- **THEN** there is no layout violation

### Requirement: Every reader checks the layout before reading the model
`la-arch-check` (except the model-free `--emit facts --top-level`) and `la-arch-diagrams` SHALL check the layout
before reading the model or views, and on any violation read nothing further. The violations SHALL be reported as
one message listing every violation, ordered by repo-relative path in code-point order and, within one file, in
file order. `la-arch-check` SHALL validate `architecture/index.yaml` first, then the layout, and exit 2 on a
violation. `la-arch-diagrams` SHALL exit 1 (cannot regenerate) on a violation. The message SHALL end by naming the
files and blocks to merge by hand into `architecture/model.c4` or `architecture/views.c4`, and SHALL NOT suggest
`la-arch-migrate`: the format check already sends a repo that predates the current format to the migration. Both
twins SHALL produce identical messages.

#### Scenario: Check refuses a violated layout
- **WHEN** `architecture/extra.c4` exists and `la-arch-check` runs
- **THEN** it exits 2 with the layout message naming `architecture/extra.c4` and prints no check finding

#### Scenario: Diagrams refuse a violated layout
- **WHEN** `architecture/views.c4` is missing and `la-arch-diagrams` runs
- **THEN** it exits 1 with the layout message and rewrites no doc

#### Scenario: Every violation in one message
- **WHEN** `architecture/views.c4` is missing, `architecture/a.likec4` exists and `architecture/model.c4` has two `model` blocks
- **THEN** one message lists all three violations in path order

#### Scenario: Legacy layout points to the migration
- **WHEN** an unversioned repo's model is in `architecture/model/app.c4`, `architecture/model.c4` does not exist, and `la-arch-check` runs
- **THEN** it exits 2 with the format check's missing-format message naming `la-arch-migrate`, before any layout message

#### Scenario: Legacy-shaped layout in a current-format repo
- **WHEN** the config declares the current format, the model is in `architecture/model/app.c4` and `architecture/model.c4` does not exist, and `la-arch-check` runs
- **THEN** it exits 2 with the layout message naming the files to merge by hand and does not mention `la-arch-migrate`

#### Scenario: Non-migratable layout names files to merge
- **WHEN** the model is in `architecture/model/app.c4` and `architecture/extra.likec4` also exists
- **THEN** the message names both files to merge by hand and does not suggest `la-arch-migrate`

#### Scenario: Index errors come first
- **WHEN** `architecture/index.yaml` is invalid and `architecture/views.c4` is missing
- **THEN** `la-arch-check` exits 2 with the index error

#### Scenario: Top-level facts ignore the layout
- **WHEN** `architecture/model.c4` is missing and `la-arch-check --language python --emit facts --top-level` runs
- **THEN** it prints the top-level facts and exits 0

### Requirement: la-arch-migrate converts the legacy layout
The repo is in the legacy layout when `architecture/model/` holds at least one `*.c4` file directly,
`architecture/model.c4` does not exist, every model file holds only `specification { }` and `model { }` blocks with
balanced braces and no other top-level text, and no LikeC4 source file exists under `architecture/` other than
those files and `architecture/views.c4`. Parse findings inside the blocks SHALL NOT prevent migration. The layout
conversion is a step of `la-arch-migrate` (see "la-arch-migrate converts the repo to the current format") and runs
only for a repo whose `living-architecture.yaml` declares no `format`.

For such a repo, `la-arch-migrate [--root DIR]` SHALL:
- when `architecture/` holds no LikeC4 source file, convert no layout;
- in the canonical layout, convert no layout;
- in any layout that is neither canonical nor legacy, print the layout message and exit 2, writing nothing;
- in the legacy layout, write `architecture/model.c4` holding one `specification { }` block with the interiors of
  every legacy `specification` block and one `model { }` block with the interiors of every legacy `model` block,
  each copied verbatim in sorted-file then file order, preceded by every comment and blank line found outside the
  legacy blocks, in that same order;
- leave an existing `architecture/views.c4` untouched, and create it as an empty `views { }` block when absent;
- before writing, verify that parsing the new layout yields the same model as parsing the legacy one — elements
  (with metadata, kinds, virtual flags and metadata problems) and relations (with their legacy flags) in order,
  and findings and metadata findings as multisets — and the same views; on any difference exit 2 writing
  nothing;
- delete every legacy `architecture/model/*.c4` and remove `architecture/model/` when it is then empty;
- print each written and each deleted path, one per line.

#### Scenario: Multi-file legacy model
- **WHEN** an unversioned repo's `architecture/model/specification.c4` and `architecture/model/python.c4` hold the model and `architecture/views.c4` exists, and `la-arch-migrate` runs
- **THEN** `architecture/model.c4` holds one `specification` and one `model` block with both files' contents in order, `views.c4` is byte-identical, `architecture/model/` is gone, the config declares the current format, and the command exits 0

#### Scenario: Single legacy file
- **WHEN** an unversioned repo's model is only in `architecture/model/model.c4`
- **THEN** `architecture/model.c4` holds its blocks and `architecture/model/` is gone

#### Scenario: Views file created when absent
- **WHEN** an unversioned legacy repo has no `architecture/views.c4`
- **THEN** `la-arch-migrate` writes `architecture/views.c4` as an empty `views { }` block

#### Scenario: Comments outside blocks kept
- **WHEN** a legacy file opens with a comment line and a blank line before its `model` block
- **THEN** that comment and blank line appear, in order, at the top of `architecture/model.c4`

#### Scenario: Parse findings carry over
- **WHEN** a legacy model has a relation with an unknown endpoint
- **THEN** the migration succeeds and `la-arch-check` reports the same finding afterwards

#### Scenario: Other files in the model directory are kept
- **WHEN** `architecture/model/README.md` sits beside the legacy `.c4` files
- **THEN** only the `.c4` files are deleted and `architecture/model/` with `README.md` remains

#### Scenario: Unversioned canonical repo
- **WHEN** an unversioned repo is in the canonical layout, no element sets `arc42` and every `cross_cutting_arc42` entry sits directly in `architecture/`, and `la-arch-migrate` runs
- **THEN** it converts no layout, stamps the format, prints only `living-architecture.yaml` as written and exits 0

#### Scenario: Unversioned repo without a model
- **WHEN** an unversioned repo has neither `architecture/index.yaml` nor any LikeC4 source under `architecture/` (or no `architecture/` at all) and `la-arch-migrate` runs
- **THEN** it converts no layout, stamps the format and exits 0

#### Scenario: Index without a model
- **WHEN** an unversioned repo has `architecture/index.yaml` but no LikeC4 source and `la-arch-migrate` runs
- **THEN** it converts no layout, stamps the format and exits 0, and `la-arch-check` then reports the missing model files

#### Scenario: Not migratable
- **WHEN** an unversioned legacy repo also holds `architecture/extra.likec4`
- **THEN** `la-arch-migrate` exits 2 with the layout message, the config is not stamped and the repo is unchanged

#### Scenario: Legacy file with a views block
- **WHEN** an unversioned repo's `architecture/model/app.c4` holds a `views { }` block
- **THEN** `la-arch-migrate` exits 2 naming that file and block and the repo is unchanged

#### Scenario: Already canonical
- **WHEN** the repo declares the current format, is in the canonical layout, and `la-arch-migrate` runs
- **THEN** it prints that there is nothing to migrate, changes nothing and exits 0

#### Scenario: Migrated repo passes the layout check
- **WHEN** an unversioned legacy repo that passed `la-arch-check` before the layout rule is migrated
- **THEN** `la-arch-check` reports exactly the findings it reported before

#### Scenario: Write failure rolls back
- **WHEN** writing or deleting fails part-way through the layout conversion of `la-arch-migrate`
- **THEN** it exits 2 and every legacy file, the `architecture/model/` directory and any pre-existing `views.c4` are byte-identical to before

### Requirement: la-arch-migrate converts the repo to the current format
`la-arch-migrate [--root DIR]` SHALL read the committed `living-architecture.yaml` as YAML only (its schema is not
checked) and:
- without a committed `living-architecture.yaml`, exit 2 with a message naming `/la:init`, writing nothing;
- when the file cannot be read, is not valid YAML or is not a mapping, exit 2, writing nothing;
- when `format` is invalid or newer than the current format, exit 2 with the format check's message, writing
  nothing;
- when `format` equals the current format, print that there is nothing to migrate, naming the format, change
  nothing and exit 0;
- when `format` is older than the current format and is not one of the released formats (the shared contract's
  list; see "Every command checks the declared format"), exit 2 naming the declared format as one no `la` release
  used, and the current format, writing nothing;
- when `format` is absent or is an older released format, convert the repo step by step, then stamp the current
  format.

There SHALL be one unversioned step, converting a repo that declares no format to the first released format: the
layout conversion (see "la-arch-migrate converts the legacy layout"), then the arc42 conversion (see "la-arch-migrate
converts the retired arc42 key format"). Every released format other than the current one SHALL have exactly one
step, converting to the next released format, and no step SHALL exist for any other source. A run SHALL apply every
step from the declared format (the unversioned step when there is none) up to the current format, in order, each
planned and verified against the repo as the earlier steps left it. No step SHALL write `living-architecture.yaml`.

Stamping SHALL be decided before any step writes. When `format` is absent, stamping SHALL insert one
`format: <current>` line, keeping every other byte of the file: after the leading comment lines, blank lines, `%`
directive lines and a `---` document marker, before the first other line, or at the end of a file that has no other
line (adding a missing final line break first); the inserted line SHALL use the file's line break (CRLF when the
file's first line break is CRLF, else LF). When `format` is present, stamping SHALL replace its value on the one line
that starts with the unquoted key `format` directly followed by a colon, when that colon is followed by spaces or
tabs, one single-line plain, single-quoted or double-quoted scalar and optionally whitespace and a comment: the
scalar, quotes included, becomes the bare current format and every other byte is kept. Any other form (no or several
such lines, a value on a later line, a block scalar, a quoted or spaced key) SHALL NOT be stamped. Before writing,
the stamped text SHALL be verified to parse to the original mapping with `format` set to the current format;
otherwise `la-arch-migrate` SHALL exit 2 with a message saying the format must be set by hand, writing nothing.

The run SHALL be all-or-nothing across every step's layout files, `architecture/index.yaml`, moved docs, deleted
files and directories, and the config: the config SHALL be replaced atomically as the last change. When a step
refuses, fails verification or hits a filesystem error, or replacing the config fails, after any change was made,
every created file SHALL be removed, every moved file moved back, and every deleted or replaced file and every
removed directory restored byte-for-byte with its mode, and the command SHALL exit 2 with that failure's message.
When restoring fails, the message SHALL name every path left changed.

On success it SHALL print the run's net effect, one path per line, each path at most once, and exit 0:
- first `wrote <path>` for each path the run wrote that exists at the end, in the order first written, with
  `living-architecture.yaml` last;
- then `moved <source> to <target>` for each moved file whose final path exists at the end, consecutive moves of one
  file composed into one move from its path before the run to its final path, in the order first moved; a file moved
  back to where it started is not reported as moved; a moved file whose contents a later step changed is also
  reported as written at its final path;
- then `deleted <path>` for each file or directory that existed before the run, does not exist at the end and is not
  the source of a reported move, in the order deleted;
- a path the run created and then removed is not reported.

For an unversioned repo this prints `architecture/model.c4`, `architecture/views.c4` and `architecture/index.yaml`
as written (each only when written), then `living-architecture.yaml`, then each moved doc, then each deleted path.

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
- **WHEN** the config declares `format: 0.3.0`, which is older than the current format and not a released format, and `la-arch-migrate` runs
- **THEN** it exits 2 naming `0.3.0` as a format no `la` release used, and the current format, and the repo is unchanged

#### Scenario: Unreleased format between released ones refused
- **WHEN** the released formats are `F1 < F3` and the config declares `F2` with `F1 < F2 < F3`
- **THEN** `la-arch-migrate` exits 2 naming `F2` and the repo is unchanged

#### Scenario: Released older format converts from its own step
- **WHEN** the released formats are `F1 < F2 < F3` and the config declares `F2`
- **THEN** `la-arch-migrate` applies only the step from `F2`, stamps `F3` and exits 0

#### Scenario: Unversioned repo applies every step
- **WHEN** the released formats are `F1 < F2` and the config declares no format
- **THEN** `la-arch-migrate` applies the unversioned step, then the step from `F1`, stamps `F2` and exits 0

#### Scenario: Every older released format has a step to the next one
- **WHEN** either twin's test suite inspects its steps against the released formats
- **THEN** there is exactly the unversioned step, targeting the first released format, and one step per released format other than the current, each targeting the next released format

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

#### Scenario: Stamp replaces an existing value
- **WHEN** the config holds `format: '0.3.0'  # repo format` after another key
- **THEN** the stamped line is `format: <current>  # repo format` and every other byte is unchanged

#### Scenario: Unstampable config
- **WHEN** the unversioned config is a flow-style mapping `{tracker: linear}`
- **THEN** `la-arch-migrate` exits 2 saying the format must be set by hand and the repo is unchanged

#### Scenario: Unstampable existing value
- **WHEN** the config's `format` value sits on the line after the key, or the key is written `format :` or `'format':`
- **THEN** the stamp is refused and the config is unchanged

#### Scenario: Stamped repo passes the format check
- **WHEN** an unversioned repo is migrated and then `la-config show` runs
- **THEN** it exits 0 and prints the current format

#### Scenario: Write failure rolls back the config too
- **WHEN** writing, deleting or replacing the config fails part-way through `la-arch-migrate`
- **THEN** it exits 2 and every legacy file, the `architecture/model/` directory, any pre-existing `model.c4` and `views.c4`, `architecture/index.yaml`, every arc42 doc and `living-architecture.yaml` are byte-identical at their original locations

#### Scenario: A later step's failure rolls back the earlier steps
- **WHEN** a run applies two steps and the second refuses, fails verification or hits a filesystem error after the first created, moved, deleted and replaced files and removed a directory
- **THEN** `la-arch-migrate` exits 2 with the second step's failure message, and every path is back with its bytes and mode, and every directory exists again

#### Scenario: Failed rollback named
- **WHEN** a write fails and restoring one of the changed paths also fails
- **THEN** `la-arch-migrate` exits 2 and its message names that path as left changed

#### Scenario: One move reported once
- **WHEN** a run moves `a` to `b` and nothing else touches either
- **THEN** it prints `moved a to b` and neither `wrote b` nor `deleted a`

#### Scenario: Consecutive moves composed
- **WHEN** one step moves `a` to `b` and a later step moves `b` to `c`
- **THEN** it prints `moved a to c` and nothing about `b`

#### Scenario: Move back not reported
- **WHEN** one step moves `a` to `b` and a later step moves `b` back to `a`
- **THEN** it prints nothing about `a` or `b`

#### Scenario: Moved then deleted
- **WHEN** one step moves the pre-existing `a` to `b` and a later step deletes `b`
- **THEN** it prints `deleted a` and nothing about `b`

#### Scenario: Created then deleted not reported
- **WHEN** one step creates `x` and a later step deletes it
- **THEN** it prints nothing about `x`

#### Scenario: Written then deleted reported as deleted
- **WHEN** one step rewrites the pre-existing `x` and a later step deletes it
- **THEN** it prints `deleted x` and not `wrote x`

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

### Requirement: la-arch-migrate refuses an unusable index.yaml
When `la-arch-migrate` converts a model (`architecture/` holds a LikeC4 source file) and `architecture/index.yaml`
exists but is not valid UTF-8, not valid YAML (a duplicate key included) or not a mapping, it SHALL exit 2 writing
nothing, printing `la-arch-migrate: ` followed by the reason in the wording `la-arch-diagrams` uses for the same
index (`c4.index-invalid-yaml`, `c4.index-duplicate-key` or `c4.index-not-mapping`). A missing `index.yaml` SHALL
convert as before. Without a model to convert, the index SHALL NOT be read.

#### Scenario: Index not valid UTF-8
- **WHEN** an unversioned legacy repo's `architecture/index.yaml` is not valid UTF-8 and `la-arch-migrate` runs
- **THEN** it exits 2 printing `la-arch-migrate: index.yaml is not valid YAML`, and every file is byte-identical

#### Scenario: Index with a duplicate key
- **WHEN** an unversioned legacy repo's `architecture/index.yaml` repeats a key and `la-arch-migrate` runs
- **THEN** it exits 2 printing `la-arch-migrate: index.yaml is not valid YAML: ` followed by the duplicate-key
  message, and every file is byte-identical

#### Scenario: Index not valid YAML
- **WHEN** an unversioned legacy repo's `architecture/index.yaml` is not valid YAML and `la-arch-migrate` runs
- **THEN** it exits 2 printing `la-arch-migrate: index.yaml is not valid YAML`, and every file is byte-identical

#### Scenario: Index not a mapping
- **WHEN** an unversioned legacy repo's `architecture/index.yaml` holds a list and `la-arch-migrate` runs
- **THEN** it exits 2 printing `la-arch-migrate: index.yaml is not a mapping`, and every file is byte-identical
