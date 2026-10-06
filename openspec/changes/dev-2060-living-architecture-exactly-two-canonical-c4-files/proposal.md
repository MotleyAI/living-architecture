## Why

The architecture model is one LikeC4 model, yet the tools read it from any number of `architecture/model/*.c4`
files and silently skip what they do not understand (a missing `views.c4`, a `views` block in a model file,
trailing blocks in `views.c4`, `.likec4` files) — while the LikeC4 CLI reads all of it. No reader owns the
definition of "the model", so ours and LikeC4's can diverge and a model spreads over ad-hoc files.

## What Changes

- **BREAKING** The model lives in exactly one file, `architecture/model.c4`, holding exactly one
  `specification { }` and one `model { }` block; views live in exactly one file, `architecture/views.c4`,
  holding exactly one `views { }` block. Any other `.c4`/`.likec4` file under `architecture/` (any depth), a
  missing or non-file canonical path, a misplaced/duplicate block, or unexpected top-level text is a layout
  violation.
- The layout is checked once, in the `c4` node, before anything reads the model: `la-arch-check` exits 2
  (setup error), `la-arch-diagrams` exits 1 (cannot regenerate), each with one message listing every
  violation. A legacy layout ends the message with "run `la-arch-migrate`"; any other layout names the files
  and blocks to merge by hand. This replaces the `c4.no-views-block` parse finding.
- The model parser reads only `architecture/model.c4`, the view parser only `architecture/views.c4`.
- `la-arch-scaffold` writes `architecture/model.c4` (one `specification` block, one `model` block holding every
  language root) and `architecture/views.c4`, and refuses when any `.c4`/`.likec4` already exists under
  `architecture/`.
- New command `la-arch-migrate` converts a legacy layout (`architecture/model/*.c4` + optional `views.c4`) to the
  canonical one by merging block interiors, verifying the parse is unchanged, writing all-or-nothing.
- The `la:living-architecture`, `la:arch-init` and `la:pr` skills and the docs describe the two-file layout.
- This repo's own model moves from `architecture/model/la.c4` to `architecture/model.c4`.

## Capabilities

### New Capabilities
- `c4-layout`: the canonical two-file LikeC4 layout, its block rules, how violations are reported by every
  reader, and the `la-arch-migrate` conversion from the legacy `architecture/model/*.c4` layout.

### Modified Capabilities
- `arch-scaffold`: the scaffold writes the two canonical files and refuses on any existing `.c4`/`.likec4`.
- `arch-check`: the "No model files" scenario now yields the layout error, and a new scenario covers a `model.c4` without roots
  (a missing file is now a layout violation, covered by `c4-layout`).

## Impact

- Code (both twins): the `c4` node (new layout check and migrator; model/view parsers read the canonical
  paths), `archcheck` (check and scaffold call the layout check; scaffold output), `cli` (new command), plus
  `shared/` (`cli.yaml`, `findings.yaml`, the source-extension constant) and every command-registration surface
  (`python/pyproject.toml` scripts, npm `package.json` bin and dispatch, packaging smoke tests).
- Conformance: every fixture's `architecture/model/*.c4` merged into `architecture/model.c4`; layout-intent
  fixtures rewritten deliberately; new cases for violations, diagrams refusal, scaffold and migrate.
- Architecture (this repo): `architecture/model/la.c4` → `architecture/model.c4`; `python.c4` gains
  `specs ['c4-layout']`.
- Downstream repos (SLayer, slayer-evals) fail `la-arch-check` until they run `la-arch-migrate` once.
