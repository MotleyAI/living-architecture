## 1. Shared contract

- [ ] 1.1 `shared/findings.yaml`: delete `refactor.map-module-unsupported`; verify no twin source or golden references it
- [ ] 1.2 `shared/languages.yaml` (typescript): the mock facts — framework receivers with their modules (`vi` ←
  `vitest`, `jest` ← `@jest/globals`) and the calls taking a module path, each with its factory argument index where
  it takes one (`mock`, `doMock`, `unstable_mockModule` with a factory; `unmock`, `doUnmock`, `dontMock`, `setMock`,
  `importActual`, `importMock`, `requireActual`, `requireMock`, `createMockFromModule` without); verify both twins'
  contract loaders accept it
- [ ] 1.3 `shared/cli.yaml`: the approved `rename` help and `--file` help, verbatim (design.md, "Approved wording")
- [ ] 1.4 `shared/schema/rename-map.schema.json`: the approved description sentence, verbatim
- [ ] 1.5 `scripts/sync-shared`; verify `scripts/sync-shared --check` passes

## 2. Tests first (pr-tests)

- [ ] 2.1 Node unit tests (Vitest): the module new-name validity rules; the taken check (each sibling extension, a
  directory with and without an `index` source, other-language siblings ignored); module-entry resolution (merge,
  `map-duplicate`); the mock-call matcher reading the shared facts (named import, aliased import, global, shadowed
  local, namespace member); `dr-mock-lint`'s factory calls read from the shared facts with unchanged findings
- [ ] 2.2 Python unit test: an invalid module new name is a resolution failure in `resolve`
- [ ] 2.3 Paired conformance (add a `node/` overlay, per-language `args` and goldens where they differ, `golden:
  manual`): `refactor-map-module-symbols`, `-duplicate`, `-converging`, `-chain`, `-taken-before-search`, `-stand-in`,
  `refactor-progress-map-module`, `refactor-rename-module-no-locator`, `-onto-module`, `-onto-package` (a directory with
  `index.ts`), `-onto-namespace-package` (a directory without an index), `-keep`, `-keep-file`, `-keep-unneeded`,
  `-keep-stale-line`, `-mixed-endings`, `-not-stand-in`, `-references` (TypeScript import forms), and the new
  `refactor-rename-module-invalid-name` (`--new-name a/b`); the Python goldens stay byte-identical
- [ ] 2.4 TypeScript adapter conformance (`golden: manual`): invalid new names (`b.ts`, `..`); taken by a `.tsx`, a
  `.js` and a `.d.ts` sibling; other-language siblings (`.json`, `.css`) not taken; a dotted stem (`a.test.ts`); a
  declaration file; `index.ts` renamed as a file; renamed to its own name; local import names stay; `--stub` refused;
  a file outside every project; new names meeting across extensions (`a.ts`, `b.tsx` → `c`); a tsconfig `files`
  entry; project references (a solution config, `app` importing and re-exporting `core`'s renamed module; rename and
  its map equal); an `--apply` map of a module and a symbol entry refused late by an unmatched line keep (git status
  clean, no destination); a specifier and an imported name in one import composed; a retarget's removed duplicate
  import meeting a module entry (`refactor.map-conflict`); a kept importer line; mock paths for a module rename (each
  Vitest and Jest call form, extensionless and `.js` styles, the Jest typed form agreeing, `paths`-mapped agreeing
  with an import of the same specifier, a shadowed `vi` and a namespace `vitest.vi` left) and for `move-module`
- [ ] 2.5 `python/tests/test_module_map_equivalence.py`: run every variant of a paired module case (per-language
  `args`), so a TypeScript `rename` equals its one-entry map byte for byte
- [ ] 2.6 Align existing tests with the plan, each file approved by the user first (the stopping policy): delete
  `refactor-map-module-typescript` and `refactor-ts-no-locator`; any node unit test pinning the module-entry refusal or
  the TypeScript no-locator finding for `rename`
- [ ] 2.7 List every new, changed and removed case in `conformance/INVENTORY.md`; verify every `findings.yaml`
  template is still produced by a golden

## 3. npm twin

- [ ] 3.1 Mock facts from the shared contract: `dr-mock-lint` reads its receivers, modules and factory calls from
  `languages.yaml`; verify `mock-lint-ts-*` cases unchanged
- [ ] 3.2 One specifier routine for module moves: the language service's file-rename edits in every relevant project
  plus mock module paths rewritten as the service rewrites an import of the same specifier; `move-module` uses it;
  verify `refactor-ts-move-module-*` cases unchanged and the new mock cases pass; a relative `declare module` naming
  a moved file rewritten like a mock path, the service's edits computed with those names masked (same length)
  (design 20); each rewritten specifier keeping its own extension style (design 21); a tsconfig `files`/`include`
  entry rewritten, the Workspace giving the service each tsconfig as a parsed JSON source (design 22)
- [ ] 3.3 Module entries in `runEntries`: the entry spec carries a module; resolution validates the new name (resolve),
  merges entries naming one file, and gives the old name; `checks` adds the taken check, not-stand-in for all-module
  runs, the moved file as a keep-able file; `references` prints the module entry's line and computes its edits and
  move; `rules` skipped when every entry is a module rename
- [ ] 3.4 Moves through the map: whole-file keeps drop a move; site resolution over edits and moves; converging new
  names refused in `conflicts`; `emit` gets every surviving move (headers in map order, edits at old paths, written
  before the moves, baseline realigned)
- [ ] 3.5 `rename` with no locator builds the one-entry module map; `renameMap` passes module entries through; remove
  the refusal and its forward-pointer comment; `retarget` with no locator still `refactor.no-locator`

## 4. Python twin

- [ ] 4.1 A module rename's invalid new name (no identifier, a keyword) refused with `refactor.cannot-rename` as a
  resolution failure in `resolve`; verify 2.2 and the paired invalid-name case

## 5. Docs and skill

- [ ] 5.1 `plugin/skills/deterministic-refactor/SKILL.md`: the approved sentences, verbatim
- [ ] 5.2 `docs/deterministic-refactoring.md`: the approved rename-map opening, verbatim

## 6. Verify

- [ ] 6.1 Local test scope per `/la:pr` (affected tests; every module, map, move-module and mock-lint conformance case
  through both twins; the equivalence suite)
- [ ] 6.2 Enforcement bundle: `la-arch-check`, LikeC4 validation, `la-typecheck`
