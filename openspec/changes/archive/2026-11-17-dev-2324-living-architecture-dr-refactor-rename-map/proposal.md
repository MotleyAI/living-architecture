## Why

`dr-refactor rename-map` cannot rename a module: `{file: pkg/mod.py, new_name: …}` is an invalid entry, and a map
holding a module entry beside any other entry refuses with `refactor.cannot-rename`. A vocabulary rename that also
renames modules therefore needs one `rename` run per module after the map (DEV-2318 needed 11). The cause is
structural: module renames run on a second pipeline that the map dispatches to before computing the union.

## What Changes

- The shared rename-map schema gains a module entry, `{module: PATH, new_name: N}`; both twins validate it and route
  on its path.
- A Python module entry, or an entry located on an import that names a module, is one entry of the union: resolved
  against the code before the map, computed on the one snapshot, checked by the one binding check with every other
  entry's edits and every move, and written all or nothing. A symbol entry inside a moved module edits that file.
  Moves inside a moved package compose.
- A module entry's taken new name is refused in the `checks` phase, before any reference search.
- `--keep` and `--stub` work across a map as for a single module rename: `--stub` stubs every moved module file and
  refuses when a module entry is not a movable module file.
- Module entries print their `references` progress item, so a lone module rename gains one stderr line.
- `rename --file F` with no locator is the one-entry map `[{module: F, new_name: N}]`.
- The TypeScript twin refuses a module entry with the new `refactor.map-module-unsupported` finding until it renames
  modules (DEV-2325).

## Capabilities

### New Capabilities

### Modified Capabilities
- `refactor`: rename maps take module entries; module renames join the map's union (routing, resolution, name
  conflicts, keeps, stubs, phases, progress and language-server start).

## Impact

- `shared/`: `schema/rename-map.schema.json`, `findings.yaml` (`refactor.map-module-unsupported`), `cli.yaml`
  (`rename-map` positional help); every twin's vendored snapshot and `CONTRACT_HASH`.
- Python twin: `refactor/` (`map_file`, `rename_map`, `module_rename`, `rename_union`, `entry_location`, `bindings`,
  `routing`, `rope_refactor`); `run_module_rename` and the `file_modules` flag are removed.
- npm twin: `src/refactor/map.ts`, `index.ts`, `routing.ts`.
- Conformance: new `refactor-map-module-*` cases; the module-rename goldens change (progress item; taken refusals lose
  `[references]`).
- Docs: `docs/deterministic-refactoring.md`, `plugin/skills/deterministic-refactor/SKILL.md`.
