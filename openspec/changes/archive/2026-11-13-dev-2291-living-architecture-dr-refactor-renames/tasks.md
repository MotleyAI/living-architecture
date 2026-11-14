## 0. Calibration (read before tests and code)

- Planning probes (scratch projects, la 0.7.0): `dr-refactor --project . rename --file pkg/mod.py --line L --col C
  --new-name dataset_name` on `def kwonly(*, model_name: str)` reproduces `cannot-rename`. Monkeypatching
  `rope.base.pyobjectsdef.PyFunction.get_param_names` before importing `rope_refactor` was enough to make the rename
  run; the design's revised split (decision 2) is what ships, not that probe.
- Existing conformance cases such as `refactor-rename-cannot-rename` show the adapter case shape (`kind: adapter`,
  `languages: [python]`, a shared `fixture:` or per-case `files/`). New cases use generated goldens
  (`LA_UPDATE_GOLDENS=1`), never `golden: manual` (design decision 9).
- `TypeFacts._decorator` (`keyed.py`) is the place overload resolution joins; it resolves decorators through
  basedpyright, never by spelling.
- Local test scope follows the `/la:pr` rule (`la-affected-tests --base main` plus every conformance case touching
  `dr-refactor rename`/`move-symbol`); the full suite is CI's job.

## 1. Tests (pr-tests stage)

- [x] 1.1 Unit tests for the rope patch: `get_param_names` with and without special args for
      `def f(a, /, b, *xs, c=0, **kw)` and each single kind; `get_parameters` holds every kind; positional binding of
      `f(1, 2, 3, c=4, d=5)` and `f(1, b=2)` gives each parameter its argument (no keyword-only slot filled
      positionally); a keyword-only parameter's object comes from rope's parameter type-hint provider (a docstring
      `:type c:`), else unknown; keyword lookup returns nothing for
      a positional-only name, `args` or `kwargs`; instance, class and static method receivers bind the first
      parameter as before. Verify they fail before the patch.
- [x] 1.2 Unit tests for a parameter's renamed declarations: hierarchy seeding on and off, located at the base and at
      an override; override with another name or no such parameter unchanged; class, static and `async def`
      methods.
- [x] 1.3 Unit tests for overload groups: resolved `typing.overload`, `typing_extensions.overload`, an aliased import,
      a same-named non-overload redefinition (no group), located at each stub and at the implementation, a group
      without an implementation, an overloaded method in a hierarchy with `--no-in-hierarchy`.
- [x] 1.4 Unit tests for the conflict check: duplicate parameter, global read, local assignment, nested scope, conflict
      in an override, deterministic first site across files and within a body, attributes and other calls' keywords
      ignored, rename to the old name a no-op (plain, hierarchy, overload group).
- [x] 1.5 Adapter (python) conformance cases, one per scenario of the delta spec (dry-run, plus `--apply` for the
      keyword-only function and the override hierarchy), including the lambda `cannot-rename` and the
      `name-conflict` refusals with every file unchanged; regression cases for `move-symbol` and a method rename over
      a mixed-kind signature.
- [x] 1.6 List every new case in `conformance/INVENTORY.md`; verify `test_conformance.py` collects them and they fail
      before the implementation for the reasons the scenarios state.

## 2. Implementation

- [x] 2.1 rope patch in `rope_patches.py` (design decision 2), installed by `apply_rope_patches`; verify 1.1 and the
      keyword-only/positional-only scenarios of 1.5.
- [x] 2.2 Overload kind in the decorator resolution and overload-group discovery (decision 5); verify 1.3.
- [x] 2.3 A parameter's renamed declarations seeded into the reference pass (decision 3); verify 1.2 and the
      hierarchy and overload cases of 1.5.
- [x] 2.4 The parameter conflict check raising `NameConflict` (decision 6); verify 1.4 and the conflict cases of 1.5.
- [x] 2.5 `plugin/languages/python.md`: apply design decision 12's approved wording verbatim.
- [x] 2.6 Generate the new goldens with `LA_UPDATE_GOLDENS=1`, review every golden diff, and verify the local test
      scope, `ruff`, `basedpyright`, `la-arch-check` and `la-typecheck` pass; confirm no existing golden changed.
- [x] 2.7 Re-run the issue's repro on SLayer's `slayer/storage/base.py` (`StorageBackend.update_column_sampled`'s
      `model_name`) as a dry-run from this checkout and confirm it renames the hierarchy and keyword call sites.

## 3. Post-merge (after the PR merges; not part of its diff)

- [ ] 3.1 Release 0.8.0: bump `python/pyproject.toml`, `node/package.json` and `plugin/.claude-plugin/plugin.json`
      together, run `scripts/release-check`, publish.
- [ ] 3.2 Pin 0.8.0 on SLayer's DEV-1607 branch; DEV-2291 stays open until the pin lands.
