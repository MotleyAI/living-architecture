## Purpose

Generate a first architecture model from the code as it is: one node per top-level unit and one arrow per
measured import edge, written atomically so the bootstrap starts from a true, checkable model.

## ADDED Requirements

### Requirement: Top-level facts need no model
`la-arch-check --language <L> --emit facts --top-level` (internal options) SHALL produce the facts document
without reading the model or views. Its edges SHALL be the measured runtime import edges attributed to the
top-level units under L's root, with one witness each, excluding self-edges. All other facts-exchange rules
(native-only serving, schema validation, identity checks, relaying failures) SHALL apply unchanged.

#### Scenario: No model on disk
- **WHEN** `index.yaml` declares `python` and no model file exists, and the top-level facts are requested
- **THEN** the document lists the top-level units and the edges between them, and the command exits 0

#### Scenario: Edge inside one unit
- **WHEN** a module of unit `core` imports another module of `core`
- **THEN** the top-level facts contain no `core -> core` edge

#### Scenario: Forwarded top-level facts
- **WHEN** the PyPI twin needs top-level facts for `typescript` and the npm twin is reachable
- **THEN** it obtains them from the npm twin's top-level facts run

### Requirement: la-arch-scaffold writes a starter architecture
`la-arch-scaffold [--root DIR]` SHALL read `architecture/index.yaml`, obtain the top-level facts of every
declared language, and write:
- `architecture/model/specification.c4`, declaring the element kinds `system`, `node` and a `#virtual`
  bucket kind, plus the tags `legacy` and `virtual`.
- `architecture/model/<language>.c4` per declared language. Its model holds the root `<language> = system '<language>'`, with one `node` per top-level unit carrying
  `metadata { package '<unit>' }`, and one relation per measured edge written inside the root.
- `architecture/views.c4` with one `view <language> of <language>` per declared language.
- `architecture/system.arc42.md` with the sections Purpose and context, Building blocks, Principles and
  Rationale, and each view's generated diagram under Building blocks.
- In `index.yaml`, `legacy_arrows: {baseline: 0}` and a `diagrams` entry mapping
  `architecture/system.arc42.md` to every view, each only if absent. All other content stays
  byte-identical.

Languages, units and edges SHALL be written in sorted order. The command SHALL print each written path, one
per line, in a fixed order, and exit 0.

#### Scenario: Python repo
- **WHEN** a Python repo with top-level units `api`, `core` and `db`, where `api` imports `core` and `core` imports `db`, runs `la-arch-scaffold`
- **THEN** the written model, views, arc42 and index match the frozen golden and the command exits 0

#### Scenario: Cycle kept
- **WHEN** unit `a` imports `b` and `b` imports `a`
- **THEN** the model has both `a -> b` and `b -> a`

#### Scenario: Unit without edges
- **WHEN** a top-level unit neither imports nor is imported
- **THEN** it still gets a node

#### Scenario: Mixed repo
- **WHEN** `index.yaml` declares `python` and `typescript`
- **THEN** one model file and one view are written per language, the kinds and tags are declared only in `architecture/model/specification.c4`, and both diagrams sit in `system.arc42.md`

#### Scenario: Scaffold passes the check
- **WHEN** a repo with no `openspec/specs/` directories is scaffolded and `la-arch-check` then runs
- **THEN** it exits 0

#### Scenario: Existing specs left unmapped
- **WHEN** a repo with `openspec/specs/billing/` is scaffolded and `la-arch-check` then runs
- **THEN** its only findings are the unmapped-spec findings, and it exits 1

### Requirement: Scaffold element ids are derived from unit names
A node's id SHALL be the last segment of its unit, with every character outside ASCII letters, digits and
`_` replaced by `_`, and with `n_` prepended when the result starts with a digit. Its title SHALL be the
unmodified last segment. Two units of one language yielding the same id SHALL be a setup error (exit 2)
naming both units.

#### Scenario: Hyphenated TypeScript unit
- **WHEN** a TypeScript top-level unit is `src/data-access`
- **THEN** its node is `data_access = node 'data-access'`

#### Scenario: Leading digit
- **WHEN** a unit's last segment is `3d`
- **THEN** its node id is `n_3d`

#### Scenario: Id collision
- **WHEN** units `src/a-b` and `src/a_b` both exist
- **THEN** the command exits 2 naming both units and writes nothing

### Requirement: la-arch-scaffold writes everything or nothing
The command SHALL refuse with exit 2 and write nothing when:
- `architecture/index.yaml` is missing or invalid;
- any `architecture/model/*.c4`, `architecture/views.c4` or `architecture/*.arc42.md` exists;
- facts cannot be obtained;
- any other setup error occurs.

It SHALL compute every output before writing any file.

#### Scenario: Existing model refused
- **WHEN** `architecture/model/app.c4` exists and `la-arch-scaffold` runs
- **THEN** it exits 2 naming that file and the repo is unchanged

#### Scenario: Missing index
- **WHEN** `architecture/index.yaml` does not exist and `la-arch-scaffold` runs
- **THEN** it exits 2 with the missing-index message and writes nothing

#### Scenario: Unreachable twin
- **WHEN** `index.yaml` declares `typescript`, the PyPI twin runs `la-arch-scaffold`, and the npm twin is unreachable
- **THEN** it exits 2 with the install hint and the repo is unchanged
