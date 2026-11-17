## 0. Stage order and conventions (read first)

- [ ] 0.1 pr-tests does section 1 only; pr-implement does sections 2–7. While section 1 is open the stage is
      `pr-tests`.
- [ ] 0.2 Every new conformance case is a Python `adapter` case, listed in `conformance/INVENTORY.md` (design
      decisions 9, 24). A case whose output on today's (rope) code is valid Python that keeps every reference bound
      gets its golden from today's code with `LA_UPDATE_GOLDENS=1`, written in pr-tests BEFORE any production change,
      reason "new case" in the commit message, and its golden diff reviewed. Every other case is `golden: manual`,
      hand-written to the spec delta. Existing Python move goldens are never regenerated.
- [ ] 0.3 The differential (section 5) compares raw edits (span and new text), rendered stdout and stderr, and
      findings. On any difference not pinned by a `golden: manual` case: STOP and ask the user (design decision 2).

## 1. Tests (pr-tests)

- [ ] 1.1 Rope-equivalence fixtures (rope-written goldens where today's output is valid; record per case which kind
      it got and why): a top-level relative import read by the moved code; aliased imports (`import a.b as c`,
      `from m import n as o`) and a star import in the source; a package `__init__.py` as the source; a moved variable,
      a moved annotated multi-line variable; a decorated class with a comment between decorators and `#` lines above
      preceded by a blank line; a comment after the body; a form-feed / whitespace-only line after the body; EOF
      without a newline; a nonliteral and an augmented `__all__`; two star imports; imports read only by a decorator
      or a default value; mixed newlines (CRLF source → LF destination, LF source → CRLF destination without a final
      newline, a BOM source) with `--apply`. Verify: each passes on today's code; any case whose today's output turns
      out invalid is raised with the user before writing its golden.
- [ ] 1.2 Spec "Python moves resolve statically without rope": "No server for a symbol move" (unit test: the language
      server factory fails if called); "rope computes nothing" (unit test: every rope entry point used by moves today
      — `create_move`, `occurrences.create_finder`, `MoveGlobal._get_moving_region`,
      `_get_moving_element_with_imports`, `rope.base.project.Project`, `libutils.modname` — patched to raise, the
      walker-gap check left working; a move-symbol and a move-module run print their goldens); "Use through a package
      that binds the module itself" (three `__init__` variants: module level, inside `if`/`try`, `__getattr__`) and
      "Use through a submodule attribute only" as conformance cases. Verify: the rope-free unit test fails on today's
      code; record which conformance cases pass on today's code.
- [ ] 1.3 Spec "Python move-symbol moves one top-level declaration": conformance cases for "Import binding or reference
      as the locator" (both forms), each form of "Not movable", "Overload group moves as one", "Decorated class with
      leading comments", "Moved variable" (`golden: manual` where 0.2 says so). Verify: the not-movable and overload
      cases fail on today's code (traceback or broken output).
- [ ] 1.4 Spec "Python refactors resolve through namespace packages": every scenario as a conformance case
      (`golden: manual`), the module-rename one included. Verify: each fails on today's code.
- [ ] 1.5 Spec "Python moves rewrite each reference minimally", new scenarios: "Destination import order", "Import used
      only by the moved code inside a block stays", "TYPE_CHECKING import follows the moved code" (both forms),
      "Other guarded import refused" (produces `refactor.guarded-import`; add the template to `shared/findings.yaml`
      with design decision 12's approved wording and run `scripts/sync-shared`), "Relative import inside the moved
      code". Verify: each fails on today's code.
- [ ] 1.6 Spec "Refactors edit only at references", "Moved code between files of different line endings": covered by
      1.1's newline cases. Verify: listed in INVENTORY.md against this scenario.
- [ ] 1.7 Package-attribute fixtures (design decision 16): `import pkg.a` then `pkg.a.f`, a re-export chain, two
      bindings of one package attribute. Verify: record which pass on today's code; any rope output that rewrites a
      use the package binds is raised with the user.
- [ ] 1.8 Unit tests: `FileChanged` for a reference-only file and a child of a moved package changed between read and
      write (design decision 21); namespace-package identity (design decision 20: `src/` layout, nested namespace, a
      submodule in two portions → unresolved) on `static_resolver` / `ProjectLayout`. Verify: the namespace tests fail
      on today's code.
- [ ] 1.9 Align existing tests with the plan (design decision 10): `python/tests/test_contract.py:625-626` to the
      renamed keys; `python/tests/test_move_edits.py` to the new entry points (signature as section 4 defines it),
      same cases and expectations. Verify: both fail on today's code only on the renamed keys / entry points.

## 2. Shared contract

- [x] 2.1 Rename `refactor.ts-move-symbol-header` → `refactor.move-symbol-header`, `refactor.ts-move-module-header` →
      `refactor.move-module-header`, `refactor.ts-moved` → `refactor.moved` in `shared/findings.yaml`;
      `scripts/sync-shared`; `node/src/refactor/typescript.ts` and `session.ts` use the new keys. Verify:
      `scripts/sync-shared --check`, `npm run lint && npm run typecheck`, `npm test`, and `scripts/conformance-cross`
      over the TypeScript move cases pass.
- [x] 2.2 `diff_render.move_description` renders `refactor.moved`. Verify: module-rename goldens unchanged.

## 3. Static resolver

- [x] 3.1 Namespace packages (design decision 20) in the module finder / `ProjectLayout`. Verify: 1.8's namespace unit
      tests and 1.4's module-rename case pass.
- [x] 3.2 `Binder` records, per import binding, its statement, item index and whether it sits in the module body or a
      block (design decision 4). Verify: a unit test over a module with body-level and block-level imports.

## 4. Move planner on the resolver (new path beside the old)

- [x] 4.1 Rebuild the planner's scopes, use lookups, name-conflict checks, "binds module" and import drops on the
      resolver's `Module` (design decision 4); references for `move-module` and `move-symbol` from the resolver,
      rule 2 as design decision 16. Verify: `test_move_edits.py` passes against the new path.
- [x] 4.2 Locator and movability (spec; design decisions 5, 7, 17). Verify: 1.3's cases pass on the new path.
- [x] 4.3 Region (design decision 19). Verify: 1.1's region cases pass on the new path.
- [x] 4.4 Destination imports (design decision 25) with guarded, `__future__` and relative-import rules (decisions
      11–14) and source-side removal limited to the module body. Verify: 1.1, 1.5 pass on the new path.
- [x] 4.5 la's project model and newlines (design decisions 5, 15, 21): `Snapshot`, `TextEdit`, `FileMove`,
      `changes_of`, `emit` with `refactor.move-symbol-header` / `refactor.move-module-header`; `moved_code=True` for
      `move-symbol`. Verify: 1.1's newline cases and 1.8's `FileChanged` tests pass on the new path.

## 5. Differential and switch

- [x] 5.1 Run old and new paths over every Python move conformance case, `test_move_edits.py`'s fixtures and section
      1's fixtures; compare as 0.3 says. Verify: no difference outside the `golden: manual` cases, or each one
      resolved with the user.
- [x] 5.2 Switch `rope_refactor.move_symbol` / `move_module` to the new path; delete `_RopeProject`, `resource`,
      `_destination`, `_rope_offset`, `rename_map.source_bytes`, `change_set_writes`, `_Scopes` / `_Scope` /
      `_Binding`, `_explicitly_binds`, `_module_object`, `_primary`, `_finder`, and every rope import in
      `move_edits.py` and `rope_refactor.py` except what the walker-gap check needs. Verify: 1.2's rope-free test
      passes; `rg -n "rope" python/src/living_architecture/refactor/move_edits.py` prints nothing.

## 6. Docs

- [x] 6.1 Apply design decision 6's approved wording verbatim to the five files. Verify: `rg -n "rope computes moves|rope for Python|with rope and" docs plugin` prints nothing.

## 7. Gates

- [x] 7.1 Local test scope (la:pr "Local test scope") passes: `uv run pytest` on the affected tests and the touched
      conformance cases; `uv run ruff check src tests`; `uv run basedpyright src tests`; `la-typecheck`.
- [x] 7.2 Enforcement bundle: `la-arch-check`, `npx likec4 validate` (or the lightest parse), `la-typecheck` against
      its baseline. Verify: all green.
- [x] 7.3 `openspec validate dev-2311-living-architecture-python-dr-refactor-moves --strict` passes.
