## Why

The TypeScript twin cannot rename a module: `rename --file x.ts --new-name N` with no locator exits with
`refactor.no-locator`, and a `rename-map` `{module, new_name}` entry, valid against the shared schema, is refused with
`refactor.map-module-unsupported`. The Python twin does both, so one entry kind of the shared contract works in only one
twin.

## What Changes

- `rename --file F --new-name N` with no locator renames the TypeScript module `F`: the file moves to `N` plus its own
  extension in the same directory, and every specifier resolving to it is rewritten. It is the one-entry map
  `[{module: F, new_name: N}]`.
- A TypeScript `{module, new_name}` entry runs in the map's one snapshot beside any other entries, with one binding
  check, one report and one all-or-nothing write. `refactor.map-module-unsupported` is removed.
- A TypeScript module's new name that is taken by a sibling (any TypeScript source or declaration file of that stem, or
  a directory of that name) is refused before any reference search; an invalid new name is refused in `resolve` in
  both twins.
- Module renames and `move-module` also rewrite the module path in Vitest/Jest mock calls; the mock facts move to
  `shared/languages.yaml`, which `dr-mock-lint` reads too.
- The module-entry conformance cases become paired where TypeScript can express them.

## Capabilities

### New Capabilities

### Modified Capabilities
- `refactor`: TypeScript module renames (no-locator `rename`, map module entries), the taken check, mock module paths
  in module renames and `move-module`, an invalid module new name refused in `resolve`, and the module rules of keeps,
  stand-in sites and cheap checks made language-neutral.

## Impact

- `node/src/refactor/` (`typescript.ts`, `rename.ts`, `session.ts`, `mocks.ts`, a module-rename unit), the Python
  module rename's new-name check (`python/src/living_architecture/refactor/module_rename.py`, `rename_map.py`).
- `shared/`: `findings.yaml` (one finding removed), `languages.yaml` (mock facts), `cli.yaml` (`rename` help),
  `schema/rename-map.schema.json` (description); every twin's vendored snapshot.
- `plugin/skills/deterministic-refactor/SKILL.md`, `docs/deterministic-refactoring.md`.
- `conformance/cases/` (paired module cases, new TypeScript cases, two removed), `conformance/INVENTORY.md`,
  `python/tests/test_module_map_equivalence.py`.
