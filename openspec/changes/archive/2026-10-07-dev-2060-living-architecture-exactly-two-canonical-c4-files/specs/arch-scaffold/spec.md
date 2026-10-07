## MODIFIED Requirements

### Requirement: la-arch-scaffold writes a starter architecture
`la-arch-scaffold [--root DIR]` SHALL read `architecture/index.yaml`, obtain the top-level facts of every
declared language, and write:
- `architecture/model.c4`, holding one `specification { }` block that declares the element kinds `system`, `node`
  and a `#virtual` bucket kind, plus the tags `legacy` and `virtual`, and one `model { }` block holding, per
  declared language, the root `<language> = system '<language>'`, with one `node` per top-level unit carrying
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
- **THEN** `architecture/model.c4` holds one `specification` block and one `model` block containing both language roots, one view is written per language, and both diagrams sit in `system.arc42.md`

#### Scenario: Scaffold passes the check
- **WHEN** a repo with no `openspec/specs/` directories is scaffolded and `la-arch-check` then runs
- **THEN** it exits 0

#### Scenario: Existing specs left unmapped
- **WHEN** a repo with `openspec/specs/billing/` is scaffolded and `la-arch-check` then runs
- **THEN** its only findings are the unmapped-spec findings, and it exits 1

### Requirement: la-arch-scaffold writes everything or nothing
The command SHALL refuse with exit 2 and write nothing when:
- `architecture/index.yaml` is missing or invalid;
- any LikeC4 source file (see `c4-layout`) exists anywhere under `architecture/`, or any
  `architecture/*.arc42.md` exists — naming the first such path in repo-relative code-point order;
- facts cannot be obtained;
- any other setup error occurs.

It SHALL compute every output before writing any file.

#### Scenario: Existing model refused
- **WHEN** `architecture/model.c4` exists and `la-arch-scaffold` runs
- **THEN** it exits 2 naming that file and the repo is unchanged

#### Scenario: Legacy model refused
- **WHEN** `architecture/model/app.c4` exists and `la-arch-scaffold` runs
- **THEN** it exits 2 naming that file and the repo is unchanged

#### Scenario: Nested LikeC4 source refused
- **WHEN** `architecture/sub/x.likec4` exists and `la-arch-scaffold` runs
- **THEN** it exits 2 naming that file and the repo is unchanged

#### Scenario: Missing index
- **WHEN** `architecture/index.yaml` does not exist and `la-arch-scaffold` runs
- **THEN** it exits 2 with the missing-index message and writes nothing

#### Scenario: Unreachable twin
- **WHEN** `index.yaml` declares `typescript`, the PyPI twin runs `la-arch-scaffold`, and the npm twin is unreachable
- **THEN** it exits 2 with the install hint and the repo is unchanged
