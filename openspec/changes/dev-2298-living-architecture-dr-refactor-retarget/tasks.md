## 0. Stage order (read first)

- [x] 0.1 `origin/main` (0.9.0, DEV-2296 archived) is merged into this branch. pr-tests writes section 1 only;
      pr-implement does sections 2–4. Spec: `specs/refactor/spec.md` ("Retarget rewrites references to an alias");
      decisions: design.md 1–18.

## 1. Tests (pr-tests)

Every conformance case below is `kind: paired` (Python and TypeScript overlays, run through both invoking twins),
`golden: manual`, listed in `conformance/INVENTORY.md`. Fixtures use the `Acme`/`Model` naming of the existing
retarget cases.

- [ ] 1.1 `shared/findings.yaml` gains `refactor.retarget-unbound: '{path}:{line}: {module} does not bind {name}, so
      nothing was refactored'`; run `scripts/sync-shared`. Verify: `scripts/sync-shared --check` passes and the
      findings-coverage test fails until 1.7 produces the template.
- [ ] 1.2 Case `refactor-retarget-imported-target` (spec "Imported target"; design 4, 5, 6): alias module imports
      TARGET from a core module, `AcmeModel = Model` (TS `export const` + `export type`), `__all__` lists only the
      alias; importers: a multi-name import from the alias module, a sole-name import (replaced in place), one already
      importing from home earlier in the block (joined), one whose home import comes later (new statement), a
      function-local import, a relative import (Python) / a `.js`-suffixed specifier (TS), a home that is a package
      `__init__` (Python `from pkg import Model`). Verify: fails today with `refactor.retarget-scope`.
- [ ] 1.3 Case `refactor-map-retarget-shared-home` (spec "Several aliases share one home import"; design 14): a
      SLayer-shaped map of three aliases imported from one home, one importer importing all three in one multiline
      parenthesised statement with a trailing comma and an inline comment, plus a fourth entry renaming one TARGET
      (the retarget writes and imports the new name). Verify: fails today.
- [ ] 1.4 Case `refactor-retarget-reexport-form` (spec "Re-export form"; design 7): Python `from pkg.core import Model
      as AcmeModel` + `__all__`; TS `export { Model as AcmeModel } from './core'` and the import-then-export form; a use
      of the alias in the re-exporting module's own body gets `Model` imported. Verify: fails today.
- [ ] 1.5 Re-bless `refactor-map-retarget-single-name-shim` (spec "Single-name shim and its importers rewritten";
      design 1): `compat` keeps its alias import and `__all__`/export, gains `Model` and its body uses `Model`; `use`
      imports `Model` from `models`. Keep `refactor-map-retarget-reexport-shim` unchanged (design 11) and extend it
      with `__all__ +=` / `.append` / `.extend` and TS `export type { }` re-exporters (design 15). Verify: the
      single-name case fails today; the re-export case passes today and after.
- [ ] 1.6 Case `refactor-retarget-star-import` (spec "Star import"): Python `from pkg.compat import *` from a
      single-name shim; a second star importer of a shim whose `__all__` exports `Model` (no import added); TS an
      importer of an `export *` barrel. Verify: fails today (Python writes an unbound `Model`).
- [ ] 1.7 Case `refactor-retarget-unbound-attribute` (spec "Unbound module attribute refused"; design 2): `import
      pkg.compat`, `import pkg.compat as c`, `from pkg import compat`, TS namespace import; exit 1, one
      `refactor.retarget-unbound` line per site; a sibling case `refactor-retarget-unbound-attribute-kept` passes
      `--keep` on each line and exits 0 with those lines unchanged. Verify: fails today.
- [ ] 1.8 Case `refactor-retarget-bound-attribute` (spec "Bound module attribute rewritten"): the module imports
      `Model`; `pkg.compat.AcmeModel()` becomes `pkg.compat.Model()`. Verify: the golden pins the rewrite.
- [ ] 1.9 Case `refactor-retarget-binding-blocks` (spec "Conditional and type-checking imports"; design 9): alias
      imports under `if TYPE_CHECKING:` (with and without `from __future__ import annotations`, a runtime use bound by a
      separate runtime import), inside `try:`/`except ImportError:`, inside a function after a module-level home
      import, and an import of `Model` in a sibling block that must not count. Python only where the form is
      Python-only (`kind: adapter`), paired otherwise. Verify: fails today.
- [ ] 1.10 Case `refactor-retarget-shadowed-kept` (spec "Kept refusal does not block"; design 13): the existing
      shadowed fixture plus `--keep` on the shadowed line; exit 0, line unchanged, other uses rewritten, no import added
      for the kept use alone, and an alias import kept while a kept use needs it. Verify: fails today (exit 1).
- [ ] 1.11 Case `refactor-ts-retarget-meanings` (spec "TypeScript type and value meanings"; design 12, `kind:
      adapter`): type-only use → `import type`; `new`/`typeof`/`extends` value uses → value import; an unrelated value
      of TARGET's spelling beside a type-only binding → `refactor.retarget-shadowed` at the value use; a merged
      class/namespace target. Verify: fails today.
- [ ] 1.12 Repurpose `refactor-retarget-scope` (spec "Other scope refused"; design 10): a member
      alias `Engine.save` with `--target Store.save_model`; stderr `refactor.retarget-scope`, exit 2; make it paired.
      Verify: the old fixture would now exit 0; the new one passes today and after.
- [ ] 1.13 Per-twin unit tests of the import planner (design 5, 6, 14, 16): join an earlier home import; replace a
      sole-name import in place; new statement after a multi-name one; relative spelling at several package depths;
      `pkg/__init__` home; TS extension style and bare package specifiers; type-only; one import per block across
      entries; `as Z` kept; name spans only (comments and parentheses intact). Python in
      `python/tests/test_retarget.py`, TypeScript in `node/test/` beside the existing rename tests. Verify: they fail
      (planner absent).

## 2. Implementation (pr-implement)

- [ ] 2.1 Target resolution in both twins (design 4, 7, 8, 9): accept an import binding or the re-export form as
      TARGET; record home, exported name, local name and identity; member aliases keep the same-class rule. Verify: 1.2,
      1.4, 1.12 pass.
- [ ] 2.2 Site classification and the bound/shadowed/unbound rules (spec bullets; design 1, 2, 9, 11, 12), replacing
      the shim/keep special cases (Python `_shim_imports`, `_through_bare_shim`, `_bare_shim`, `_module_binds_other`;
      TS `keptBindings`, `shimImports`) with the one rule. Verify: 1.5–1.9, 1.11 pass.
- [ ] 2.3 The import planner, run after `--keep` and once over all retarget entries of a map (design 5, 6, 13, 14,
      16); `--keep` releases shadowed/unbound refusals. Verify: 1.3, 1.10, 1.13 pass.
- [ ] 2.4 Apply the approved wording (design 3) verbatim to `plugin/skills/deterministic-refactor/SKILL.md` and
      `docs/deterministic-refactoring.md`. Verify: diff shows exactly those sentences.

## 3. Gates

- [ ] 3.1 Local test scope green in both twins; `ruff`, `basedpyright`, `npm run lint && npm run typecheck`,
      `la-arch-check`, `la-typecheck`, `scripts/sync-shared --check`, `scripts/conformance-cross` over the touched
      cases. Verify: all exit 0.

## 4. Acceptance

- [ ] 4.1 From this checkout, dry-run on SLayer's DEV-1607 worktree
      (`~/GitHub/SLayer/slayer.worktrees/egor__dev-1607-rename-columns-to-fields-to-be-consistent-with`) the map
      `slayer/flight/catalog.py` `FlightCatalog`/`FlightSchema`/`FlightTable`/`FlightMetric`/`FlightDimension` →
      `Facade*`. Expect `handlers.py` and `info_schema.py` re-pointed to one `from slayer.facade.catalog import ...`
      each, `catalog.py` unchanged, exit 0. Record the commit, outcome and wall time here.
- [ ] 4.2 `openspec validate dev-2298-living-architecture-dr-refactor-retarget --strict` before archiving.
