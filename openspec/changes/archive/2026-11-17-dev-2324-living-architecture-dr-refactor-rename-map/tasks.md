## 1. Shared contract

- [x] 1.1 `shared/schema/rename-map.schema.json`: the entry is either today's form or `{module, new_name}` (no `file`,
  locator or `retarget`); append the approved description sentence (design.md, "Approved wording")
- [x] 1.2 `shared/findings.yaml`: add `refactor.map-module-unsupported` with the approved text
- [x] 1.3 `shared/cli.yaml`: the `rename-map` positional `map` help, approved text; the `rename-map` `--stub` option (rename's, help as above)
- [x] 1.4 `scripts/sync-shared`; `scripts/sync-shared --check` passes

## 2. Tests first (pr-tests)

- [x] 2.1 Python unit tests: map loading of module entries and invalid forms; routing on `module`; one module
  identity for path- and import-located entries (module, `__init__.py`, module under a namespace package; merge and
  `map-duplicate`); the final-path map (both entry orders, three levels, two moves converging -> name-conflict);
  the together check with composed moves; `--stub` eligibility (file, package, namespace package, library alias)
- [x] 2.2 Python equivalence test: every `conformance/cases/refactor-rename-module-*` case run as its one-entry map
  (`{module: …}` for `--file` without a locator, the locator entry otherwise) gives identical stdout, stderr and exit
- [x] 2.3 Node unit tests: `loadMap` accepts module entries and rejects the invalid forms; map language from `module`;
  the TypeScript refusal in index order before any phase line
- [x] 2.4 Conformance (Python adapter, `golden: manual`): `refactor-map-module-symbols` (module + class inside it +
  importer's function, `--apply`), `refactor-map-module-import-located`, `refactor-map-module-duplicate`,
  `refactor-map-module-nested` (`--apply`, git status), `refactor-map-module-nested-three`,
  `refactor-map-module-converging`, `refactor-map-module-init-binding`, `refactor-map-module-chain` (checks-phase
  name-conflict), `refactor-map-module-taken-before-search`, `refactor-map-module-stub`,
  `refactor-map-module-stub-package`, `refactor-map-module-stub-alias`, `refactor-map-module-keep-child`,
  `refactor-map-module-keep-package`, `refactor-map-module-stand-in`, `refactor-progress-map-module`
- [x] 2.5 Conformance (neutral, both invoking twins): `refactor-map-module-invalid`, `refactor-map-module-typescript`
  (produces `refactor.map-module-unsupported`), `refactor-map-module-mixed-languages`
- [x] 2.6 Align existing goldens with the plan (per-file approval from the user before editing, as the stopping policy
  requires): the four `refactor-rename-module-onto-*` cases drop `[references]`; every lone module-rename case gains
  its `[references 1/1]` line; the stub-refused cases' stderr
- [x] 2.7 List every new case in `conformance/INVENTORY.md`

## 3. Python twin

- [x] 3.1 `map_file`: load module entries; map language from `file` or `module`
- [x] 3.2 One module identity routine shared by the path entry and `EntryLocator.at` on an import
- [x] 3.3 `ModuleRename` becomes a `MapRename`: edits plus one move; taken check exposed for `checks`
- [x] 3.4 `RenameMap`: drop the `len(out) > 1 and any(is_module)` refusal; taken and `--stub` checks in `checks`;
  `--with`/`--without` refused in `checks` only when every entry is a module rename; server start and `rules` skipped
  only when every entry is a module rename; progress item for module entries
- [x] 3.5 The final-path map: every surviving move composed, innermost first; name-conflict for two files at one path;
  passed to every `BindingCheck` (alone: the entry's own move; together: all)
- [x] 3.6 Keeps over edits and moves (directory keeps cover moves under them); site resolution once over the union
- [x] 3.7 Output: headers in map order, edits at old paths, one move pair per entry, stubs for every moved module file,
  baseline realigned through the final-path map; writer moves innermost first
- [x] 3.8 `rename --file F` with no locator builds `[{module: F, new_name: N}]`; remove `run_module_rename`, the
  `module_rename` callback and `file_modules`

## 4. npm twin

- [x] 4.1 `map.ts`: `MapEntry` with optional `module`; `index.ts` map language from `file` or `module`
- [x] 4.2 Refuse module entries with `refactor.map-module-unsupported`, every one in index order, before any phase
  line, exit 2; code comment pointing to DEV-2325 (forward pointer)

## 5. Docs and skill

- [x] 5.1 `plugin/skills/deterministic-refactor/SKILL.md`: the approved rename-map sentence, verbatim
- [x] 5.2 `docs/deterministic-refactoring.md`: the approved rename-map sentence, verbatim

## 6. Verify

- [x] 6.1 Local test scope per `/la:pr` (affected tests, the module and map conformance cases, both twins'
  conformance runs for the neutral cases)
- [x] 6.2 Enforcement bundle: `la-arch-check`, LikeC4 validation, `la-typecheck`
