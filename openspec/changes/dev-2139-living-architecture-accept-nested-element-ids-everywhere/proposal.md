## Why

`la-arch-check` enforces the import law between elements at every depth, yet every other surface that takes an
element id accepts only nodes (direct children of a language root): `cross_cutting_specs.touches` reports a nested
element as an unknown node, nested elements cannot own spec groups, and views cannot include or anchor on them. A spec
can therefore only attach at a coarser granularity than the boundaries the model enforces. The arc42 side has the same
split: a doc is named both by an `arc42` metadata pointer and by a filename convention, and docs outside the top level
of `architecture/` escape the orphan and tag checks.

## What Changes

- Every element (language root, node or nested element) MAY carry `metadata { specs [...] }`; the mapping keys
  (`package`, `claims`, `packages`) stay node-only. A mapping key on a root or nested element is a setup error.
- `cross_cutting_specs.touches` accepts any element id at any depth, roots included.
- **BREAKING**: the `arc42` metadata key is retired. An element's arc42 doc is `architecture/<element id>.arc42.md`
  (optional). A model still using the key makes `la-arch-check` exit 2.
- **BREAKING**: every arc42 doc sits directly in `architecture/`; a `*.arc42.md` in a subfolder, a
  `cross_cutting_arc42` entry elsewhere, or one naming an element's doc is a finding. The orphan check recognises
  element docs by id.
- `la-arch-migrate` converts the `arc42` key format (moving docs, dropping the key, renaming `diagrams` keys,
  flattening cross-cutting docs) in canonical as well as legacy repos, all-or-nothing, as a step of migrating a repo
  that declares no `format` to format 0.4.0.
- Views: `include X`, `X -> *` and `* -> X` accept elements at any depth, relative to the root; depth counts from the
  selected element. `view ... of` stays root-only.
- Findings say "element" where they apply: `spec-mapping.unknown-node` becomes `spec-mapping.unknown-element`;
  `arc42-exists.node-doc-missing`, `arch-check.metadata-on-root`, `arch-check.metadata-on-nested`,
  `c4.include-non-top-level` and `c4.view-includes-non-top-level` are removed; new arc42-exists and arch-check
  templates are added.
- Skills in `plugin/skills/` say "element" and name the flat, id-named arc42 docs.
- Version 0.4.0 in both twins and the plugin.

## Capabilities

### New Capabilities

### Modified Capabilities
- `arch-check`: element metadata, spec ownership and `touches` at any depth; id-named flat arc42 docs; nested ids in
  views.
- `c4-layout`: migrating an unversioned repo to the current format also converts the retired `arc42` key format, in
  canonical repos too.

## Impact

- `shared/`: `findings.yaml` templates, `schema/node.schema.json` (`$defs/element`, no `arc42`), `cli.yaml` help for
  `la-arch-migrate`; re-vendored into both twins.
- Python twin `python/src/living_architecture/{archcheck,c4}` and npm twin `node/src/{archcheck,c4}`: element map,
  docs/spec-mapping checks, views expansion, migration.
- Conformance corpus: new and replaced cases, `INVENTORY.md`.
- `plugin/skills/{living-architecture,pr,pr-plan,pr-review,pr-implement,arch-init,arch-cleanup}/SKILL.md`.
- Adopter repos using `arc42` keys or nested arc42 docs must run `la-arch-migrate`.
