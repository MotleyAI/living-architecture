## Purpose

Pin where the LikeC4 model and views live — exactly `architecture/model.c4` and `architecture/views.c4` — so every
reader, ours and the LikeC4 CLI's, sees the same single model, and convert repos from the legacy multi-file layout.

## ADDED Requirements

### Requirement: The model and views live in two canonical files
`architecture/` SHALL hold exactly two LikeC4 source files: `architecture/model.c4` and `architecture/views.c4`.
A LikeC4 source file is a file whose name ends, case-sensitively, in one of the extensions listed in the shared
contract (`.c4`, `.likec4`). The following SHALL each be a layout violation:
- a canonical file that does not exist, or whose path exists but is not a regular file (or a symlink to one);
- any other LikeC4 source file under `architecture/`, at any depth; symlinks to files count as files, symlinked
  directories are not descended into.

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
violation. `la-arch-diagrams` SHALL exit 1 (cannot regenerate) on a violation. When the repo is in the legacy
layout (see "la-arch-migrate converts the legacy layout") the message SHALL end with the instruction to run
`la-arch-migrate`; otherwise it SHALL name the files and blocks to merge by hand into `architecture/model.c4` or
`architecture/views.c4`. Both twins SHALL produce identical messages.

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
- **WHEN** the model is in `architecture/model/app.c4` and `architecture/model.c4` does not exist
- **THEN** the message ends with the instruction to run `la-arch-migrate`

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
those files and `architecture/views.c4`. Parse findings inside the blocks SHALL NOT prevent migration.

`la-arch-migrate [--root DIR]` SHALL:
- in the canonical layout, print that there is nothing to migrate and exit 0;
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
- write all-or-nothing: on a filesystem error restore every deleted file byte-for-byte and the directory, remove
  only the files it created, and exit 2;
- print each written and each deleted path, one per line, and exit 0.

#### Scenario: Multi-file legacy model
- **WHEN** `architecture/model/specification.c4` and `architecture/model/python.c4` hold the model and `architecture/views.c4` exists, and `la-arch-migrate` runs
- **THEN** `architecture/model.c4` holds one `specification` and one `model` block with both files' contents in order, `views.c4` is byte-identical, `architecture/model/` is gone, and the command exits 0

#### Scenario: Single legacy file
- **WHEN** the model is only in `architecture/model/model.c4`
- **THEN** `architecture/model.c4` holds its blocks and `architecture/model/` is gone

#### Scenario: Views file created when absent
- **WHEN** a legacy repo has no `architecture/views.c4`
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

#### Scenario: Already canonical
- **WHEN** the repo is in the canonical layout and `la-arch-migrate` runs
- **THEN** it prints that there is nothing to migrate, changes nothing and exits 0

#### Scenario: Not migratable
- **WHEN** a legacy repo also holds `architecture/extra.likec4`
- **THEN** `la-arch-migrate` exits 2 with the layout message and the repo is unchanged

#### Scenario: Legacy file with a views block
- **WHEN** `architecture/model/app.c4` holds a `views { }` block
- **THEN** `la-arch-migrate` exits 2 naming that file and block and the repo is unchanged

#### Scenario: Migrated repo passes the layout check
- **WHEN** a legacy repo that passed `la-arch-check` before the layout rule is migrated
- **THEN** `la-arch-check` reports exactly the findings it reported before

#### Scenario: Write failure rolls back
- **WHEN** writing or deleting fails part-way through `la-arch-migrate`
- **THEN** it exits 2 and every legacy file, the `architecture/model/` directory and any pre-existing `views.c4` are byte-identical to before
