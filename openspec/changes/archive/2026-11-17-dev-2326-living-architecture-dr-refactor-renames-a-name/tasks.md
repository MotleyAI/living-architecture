## 1. Tests first (pr-tests)

- [x] 1.1 Fixture `conformance/fixtures/refactor-tuple-targets` (Python) and adapter cases (`languages: [python]`),
  one per scenario of "Python renames reach names bound by tuple targets": function local by `--symbol` and by
  `--line`/`--col`, module level, class body (`C.y`), starred, nested (`c`, then `b`), `await` right-hand side,
  comprehension target, nested-scope binding of the same spelling, call keyword of the same spelling, and one
  `rename-map` holding several entries. Goldens via `LA_UPDATE_GOLDENS=1` (new cases), reviewed; list every case in
  `conformance/INVENTORY.md`. These pass on `main` by design (regression pins); verify with
  `uv run pytest -q tests/test_conformance.py -k tuple-target` in `python/`.
- [x] 1.2 Fixture `conformance/fixtures/refactor-move-shadowing` (Python) and adapter cases, one per new scenario of
  "Python moves rewrite each reference minimally": parameters of every kind, a lambda and a comprehension target
  shadowing an import alias (`move-module`); a function-local alias import; a function scope that also assigns the
  alias; `global` and `nonlocal`; a `nonlocal` declaration keeping its enclosing import; a comprehension's first
  iterable; defaults and annotations; the moved symbol
  shadowed in its source module (`move-symbol`, no import added there); a star-import consumer shadowing the moved
  name. Goldens via `LA_UPDATE_GOLDENS=1`, then hand-check each shadowed use is unchanged and each eligible use is
  rewritten (the lambda, comprehension-target and source-module cases must fail on `main`); list them in
  `INVENTORY.md`.
- [x] 1.3 Unit tests in `tests/test_move_edits.py` for the `_Scopes` fixes: a `global`/`nonlocal` name binds in the
  scope the statement names, not the declaring one; a comprehension's first iterable is read in the enclosing scope.
  Verify they fail on `main`.
- [x] 1.4 Unit test in `tests/test_python_source.py`: `every_parameter` returns every parameter kind of a `def` and
  a `lambda` in declaration order. Test in `tests/test_symbol_paths.py`: `--symbol f(a)` locates a parameter of
  each of the five kinds. Verify the first fails (import error) on `main`.
- [x] 1.5 Codex-review the tests against this change (when `reviewers.codex` is on).

## 2. Remove the evaluator patch

- [x] 2.1 In `refactor/rope_patches.py` delete `_rope_primary_and_pyname_at`, `_ParameterSites`, `_parameter_sites`,
  `_primary_and_pyname_at` and the `evaluate.ScopeNameFinder.get_primary_and_pyname_at` line of
  `apply_rope_patches`, the imports that become unused, and the module docstring's lambda sentence; keep the walker,
  `async def` header, function-model and call-argument patches. Verify `ruff` and `basedpyright` are clean.
- [x] 2.2 In `tests/test_rope_parameters.py` delete the four evaluator-level tests named in design.md decision 3 and
  their `tests/durations/suite.json` entries; verify the rest of the file passes.

## 3. `every_parameter`

- [x] 3.1 Move `every_parameter` to `refactor/python_source.py`; `rename_union.py` and `retarget.py` import it there;
  `symbol_path.py` uses it instead of `_every_parameter` (deleted). Verify task 1.4's tests pass.

## 4. Moves: scope fixes and the lexical veto

- [x] 4.1 `_Scopes`: a `global` name binds in the module scope and a `nonlocal` name in the nearest enclosing function
  scope that binds it, never in the declaring scope; a comprehension's first iterable is visited in the enclosing
  scope. Verify task 1.3 passes.
- [x] 4.2 One occurrence-eligibility check (design.md decision 10) used by `_ModuleMove.rewrite_uses`,
  `_SymbolMove._rewrite_uses` and `_SymbolMove._outside`; the star-import path keeps its own check. Verify task 1.2
  passes and every existing `refactor-move-*` golden is byte-identical.
- [x] 4.3 Uses rope's finder misses (a `def` header's defaults and annotations, a comprehension's first iterable) found
  from `_Scopes` (design.md decision 10): each dotted chain rooted at an import binding, resolved from that binding's
  module path, joins rope's occurrences, skipping positions rope already reports. Verify the `refactor-move-shadowing-defaults`
  and `-first-iterable` cases pass.

## 5. Gates

- [x] 5.1 Local test scope per `/la:pr` (`la-affected-tests --base main` plus the conformance cases above and every
  `refactor-*` case), `uv run ruff check src tests`, `uv run basedpyright src tests`, the new cases through both
  twins with `scripts/conformance-cross`, and the enforcement bundle (`la-arch-check`, LikeC4 validation,
  `la-typecheck`); all green. Gotcha: this worktree has no `node/node_modules`, so `la-arch-check` (it needs the
  TypeScript twin) and `scripts/conformance-cross` fail until `npm ci && npm run build` runs in `node/`.

## 6. Tracker and handoff

- [ ] 6.1 DEV-2326 stays open after merge until task 7 is done.

## 7. Post-merge (outside this PR)

- [ ] 7.1 A separate release commit (minor bump of `python/pyproject.toml`, `node/package.json` and
  `plugin/.claude-plugin/plugin.json` together) carrying #54, #56 and this change; published.
- [ ] 7.2 SLayer's `living-architecture` pin moves to that release; then DEV-2326 goes to Done.
