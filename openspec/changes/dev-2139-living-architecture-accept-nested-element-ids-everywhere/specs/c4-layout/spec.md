## MODIFIED Requirements

### Requirement: la-arch-migrate converts the legacy layout
The repo is in the legacy layout when `architecture/model/` holds at least one `*.c4` file directly,
`architecture/model.c4` does not exist, every model file holds only `specification { }` and `model { }` blocks with
balanced braces and no other top-level text, and no LikeC4 source file exists under `architecture/` other than
those files and `architecture/views.c4`. Parse findings inside the blocks SHALL NOT prevent migration. The repo uses
the arc42-key format when any model element's metadata sets `arc42`, or a `cross_cutting_arc42` entry in
`architecture/index.yaml` is not `architecture/<name>.arc42.md` with no `/` in `<name>`.

`la-arch-migrate [--root DIR]` SHALL:
- in the canonical layout without the arc42-key format, print that there is nothing to migrate and exit 0;
- in any layout that is neither canonical nor legacy, print the layout message and exit 2, writing nothing;
- in the legacy layout, stage `architecture/model.c4` holding one `specification { }` block with the interiors of
  every legacy `specification` block and one `model { }` block with the interiors of every legacy `model` block,
  each copied verbatim in sorted-file then file order, preceded by every comment and blank line found outside the
  legacy blocks, in that same order; leave an existing `architecture/views.c4` untouched, and stage it as an empty
  `views { }` block when absent; stage the deletion of every legacy `architecture/model/*.c4` and the removal of
  `architecture/model/` when it is then empty;
- in the arc42-key format, applied to the canonical model or to the staged one: for each element setting
  `arc42 '<p>'`, in model order, stage the move of `<p>` to `architecture/<element id>.arc42.md` (no move when they
  are equal), the removal of the `arc42` line, and the removal of the element's `metadata` block when it is then
  empty; for each `cross_cutting_arc42` entry `<p>` not of the flat form, stage the move of `<p>` to
  `architecture/<basename of p>` and the rewrite of the entry; stage the rename of every `diagrams` key equal to a
  moved source to its target. Every other byte of `architecture/model.c4` and `architecture/index.yaml` SHALL stay
  unchanged;
- exit 2 writing nothing, naming the paths, when a source does not exist, a source is moved more than once, two
  sources share a target, or a target already exists as a file or as a `diagrams` key and is not its own source;
- before writing, verify that the staged result parses to the same model as the input apart from the removed `arc42`
  keys and emptied `metadata` blocks (elements with metadata, kinds, virtual flags and metadata problems, and relations
  with their legacy flags, in order; findings and metadata findings as multisets), to the same views, to an
  `index.yaml` equal to the input with the staged entry and key renames, and that every moved doc is byte-identical
  to its source; on any difference exit 2 writing nothing;
- write all-or-nothing: on a filesystem error restore every overwritten, moved and deleted path byte-for-byte at its
  original location, and the removed directory, remove only the files it created, and exit 2;
- print each written, moved and deleted path, one per line, and exit 0.

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
- **WHEN** the repo is in the canonical layout without the arc42-key format and `la-arch-migrate` runs
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
- **WHEN** writing, moving or deleting fails part-way through `la-arch-migrate`
- **THEN** it exits 2 and every legacy file, the `architecture/model/` directory, `architecture/index.yaml`, every arc42 doc and any pre-existing `model.c4` and `views.c4` are byte-identical at their original locations

#### Scenario: Canonical repo with arc42 keys
- **WHEN** a canonical repo's node `python.api` sets `arc42 'architecture/api.arc42.md'` and `index.yaml` maps `architecture/api.arc42.md: [api]` under `diagrams`
- **THEN** the doc is moved byte-identically to `architecture/python.api.arc42.md`, the `arc42` line is gone, the `diagrams` key is renamed, every other byte of `model.c4` and `index.yaml` is unchanged, and the command exits 0

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
- **WHEN** a legacy-layout repo's model sets an `arc42` key
- **THEN** one run writes `architecture/model.c4` without the key, moves the doc, and `la-arch-check` reports no arc42-exists finding for it

#### Scenario: Missing source refused
- **WHEN** a node sets `arc42 'architecture/gone.arc42.md'` and that file does not exist
- **THEN** `la-arch-migrate` exits 2 naming `architecture/gone.arc42.md` and the repo is unchanged

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
