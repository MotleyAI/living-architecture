## 1. Shared contract

- [ ] 1.1 Add `refactor.unlinked-keyword`, change `refactor.blindspots` to `{names}`, and change `refactor.unsure-warning`
      and the three `--allow-blindspots` help texts in `shared/findings.yaml` and `shared/cli.yaml`, each verbatim from
      design.md decision 22; verify with `scripts/sync-shared` then `scripts/sync-shared --check` (exit 0)
- [ ] 1.2 Allow `Never` as a `{type}` of `compliance.attr-blindspot` wherever the shared schema or the twins enumerate its
      values; verify the drift and schema tests of both twins pass

## 2. Tests first (pr-tests)

- [ ] 2.1 Add the Python adapter conformance cases, hand-written goldens (`golden: manual`), each failing before the fix:
      `refactor-rename-param-decorated`, `refactor-rename-param-decorated-unlinked`,
      `refactor-rename-param-decorated-unlinked-allow`, `refactor-rename-param-decorated-unlinked-unsure`,
      `refactor-rename-field-kwargs-flow`, `refactor-rename-field-kwargs-unresolved`,
      `refactor-rename-field-kwargs-unrelated`, `refactor-rename-param-kwargs-flow`,
      `refactor-rename-keyword-untyped-callee`, `compliance-attr-blindspot-never`, `refactor-rename-blindspot-never`;
      verify each runs and fails through `uv run pytest -q tests/test_conformance.py -k <case>` in `python/`
- [ ] 2.2 Add the paired case `refactor-rename-constructor-param-siblings` (Python: sibling `__init__`, a forwarding
      subclass, sibling `__new__`, an overloaded `__init__`, a class declaring both constructors; TypeScript: sibling
      classes with a same-named constructor parameter); verify the Python side fails and the TypeScript side runs through
      `scripts/conformance-cross`
- [ ] 2.3 The unresolved-carrier fixture holds one carrier per unresolved use (alias, `dict(kw)`, `kw.copy()`,
      `base.update(kw)`, `base | kw`, plain argument, `return kw`, iteration, `kw.items()`, variable key, rebinding, nested
      function reading `kw`, a two-carrier cycle), a mixed-sink carrier and a dict literal unpacked into an unresolved
      carrier; the flow fixture holds a nested scope shadowing `kw`; verify the golden lists exactly those calls
- [ ] 2.4 List every new case in `conformance/INVENTORY.md`, naming `refactor.unlinked-keyword` against the goldens that
      produce it; verify the inventory test passes
- [ ] 2.5 Unit tests in `python/tests/` for: the signature fact of the export (per callable alternative, overloads and
      unions), the carrier verdict join (renamed, other, mixed, unresolved, chains, cycle), the constructor rule in the
      hierarchy, the `Never` verdict and its `{type}` precedence, and the parenthesised `{receiver}`; verify they fail
      before the fix
- [ ] 2.6 Scenarios with no conformance case get a unit or integration test: "No extra request without unresolved
      keywords" (count the export requests), "Members and keywords in one report", "Kept line", "Keyword collision through
      a carrier", "Aliased field"

## 3. Keyword linking through the checker's signature

- [ ] 3.1 Export a position fact for a call keyword: for each callable alternative the checker considers at the call,
      whether its signature binds that name by keyword; verify with the unit tests of 2.5 against `@contextmanager`,
      a `ParamSpec` decorator, `functools.lru_cache` and an untyped decorator
- [ ] 3.2 In the probe round, rename the renamed declarations in memory and link each unresolved `old=` keyword whose
      every alternative binds `old` before and `new` after; verify `refactor-rename-param-decorated` passes and a run
      without unresolved keywords sends no extra export request
- [ ] 3.3 Add the index cache key for the new fact and the probe texts; verify the cache tests pass and output is
      identical with and without a cache entry

## 4. `**kwargs` carriers

- [ ] 4.1 One carrier analysis over a `def`'s `**kw` name: sinks, key forms, neutral uses, resolved or unresolved;
      verify with the unit tests of 2.5
- [ ] 4.2 Sink targets for keyed classes, functions and methods, other classes (the constructor the checker resolves),
      `super().__init__`, carriers, and dict literals holding `**kw`; verdict join with chains and cycles; verify
      `refactor-rename-field-kwargs-flow`, `refactor-rename-param-kwargs-flow` and
      `refactor-rename-field-kwargs-unrelated` pass
- [ ] 4.3 Rewrite carrier call keywords, constant keys of dict literals unpacked into a carrier or into a function or
      constructor, and key-form strings, under the alias, plain-literal and collision rules of typed dict keys; verify the
      collision and alias tests of 2.6 pass
- [ ] 4.4 Re-bless `conformance/cases/refactor-rename-param-unresolved-keywords` with `LA_UPDATE_GOLDENS=1` (reason: the
      `wrap` keyword and the dict-literal key are now renamed with the parameter), add a `kwonly(**mapping)` call to its
      fixture, and review the golden diff: only those two sites change

## 5. Unlinked keywords as blind spots

- [ ] 5.1 Find unlinked keywords for parameter renames and keyed-field renames (the four conditions of the
      requirement) and file them with the run's blind spots: sorted, `--keep`, `--allow-blindspots`, `--unsure include`;
      verify `refactor-rename-param-decorated-unlinked` and its `-allow` and `-unsure` variants,
      `refactor-rename-field-kwargs-unresolved` and `refactor-rename-keyword-untyped-callee` pass
- [ ] 5.2 Format `refactor.blindspots` with `{names}` (`.old` for a member, `old=` for a keyword) in single renames and
      rename maps; verify every existing blind-spot golden is byte-identical and the mixed-report test of 2.6 passes

## 6. `Never` receivers and the receiver text

- [ ] 6.1 Count `Never` as an untyped receiver verdict in the export, with `{type}` precedence `Unknown`, `Any`, `Never`;
      verify `compliance-attr-blindspot-never` and `refactor-rename-blindspot-never` pass and report the same positions
- [ ] 6.2 Keep the parentheses written around a receiver in `{receiver}`; check the TypeScript twin on
      `(a as any).id` and align it if it differs; re-bless any golden that gains parentheses with that stated reason and
      review the diff

## 7. Constructors

- [ ] 7.1 Give `__init__` and `__new__` no hierarchy in a parameter rename (the located `def` and its overload group
      only); verify `refactor-rename-constructor-param-siblings` passes in both twins and the existing
      `refactor-rename-param-override*` and `refactor-rename-param-overload-method*` cases are unchanged

## 8. Skill and docs

- [ ] 8.1 Edit `plugin/skills/deterministic-refactor/SKILL.md` (step 4 bullet, step 6 gate bullet) and
      `docs/deterministic-refactoring.md` verbatim from design.md decision 22; verify with
      `npx -y @anthropic-ai/claude-code plugin validate plugin`
- [ ] 8.2 Describe the new blind spot and the carrier rule in `docs/refactoring-internals.md` where it lists the rules;
      verify the docs tests pass

## 9. Gates

- [ ] 9.1 Python twin: `uv run ruff check src tests`, `uv run basedpyright src tests` and the local test scope
      (`la-affected-tests --base main` plus the conformance cases above) pass
- [ ] 9.2 npm twin: `npm run lint && npm run typecheck`, the affected Vitest files and `npm run build && npm run
      conformance` for the changed and new cases pass
- [ ] 9.3 `la-arch-check`, `npx likec4 validate` and `la-typecheck` pass; `scripts/sync-shared --check` exits 0
- [ ] 9.4 Re-run the four repro projects of the tracker issue (rebuilt from its Agent notes) and confirm each gives the
      output the spec states
