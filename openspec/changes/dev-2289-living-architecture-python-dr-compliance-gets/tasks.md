## 1. Tests (pr-tests stage)

- [ ] 1.1 Python unit tests for every scenario of "Python explicit-any compliance check" (spellings, non-annotation
      sites, aliases not followed, forward references and type comments, non-forward strings, shadowing and mixed
      bindings, scoping incl. comprehension / `nonlocal` / except-handler / match bindings, first-party re-exports,
      `__all__` and private names, cycle, non-first-party modules incl. a local `typing.py`, `src/` layout, a
      directory without `__init__.py` below the root, parse error); they fail before implementation
- [ ] 1.2 Python test that the finding renders `Any` / `object`; contract tests of both twins pin `any_type` /
      `top_type` and the parameterised `compliance.explicit-any` template (`python/tests/test_contract.py` and the
      node contract test)
- [ ] 1.3 Conformance: new Python adapter cases covering the spec scenarios at command level (at least: nested and
      variadic, every spelling, outside annotations, forward refs and type comments, first-party re-exports, a
      default run without `--select` that reports `Any`), listed in `conformance/INVENTORY.md`; goldens hand-written
      (`golden: manual`)
- [ ] 1.4 Switch `compliance-select-other-language-check` to `--select tsconfig` and its spec scenario wording;
      `compliance-all-checks` and its `k.py` stay unchanged
- [ ] 1.5 Review every golden the change reaches (e.g. `twin-dr-compliance-forwarded-files`, `compliance-help`) and
      adjust only with a stated reason

## 2. Shared contract

- [ ] 2.1 `shared/languages.yaml`: Python `compliance_checks` becomes `[untyped-def, unannotated-attr, explicit-any,
      mock, rope-walk]`; add `any_type` / `top_type` to both languages and document them in the header comment
- [ ] 2.2 `shared/findings.yaml`: `compliance.explicit-any` takes `{any}` / `{top}` (approved wording in design.md
      decision 4); `shared/cli.yaml`: the `dr-compliance` help lists `explicit-any` among Python's checks
- [ ] 2.3 Run `scripts/sync-shared`; `scripts/sync-shared --check` passes

## 3. Python twin

- [ ] 3.1 New check module in `living_architecture.refactor` implementing resolution per the spec (reuse `lang`'s
      Python import helpers where they fit; AST only, no import of target code); wire it into `compliance.py`'s
      `check_path` under `explicit-any`; update the module docstring's check list; unit tests from 1.1/1.2 pass
- [ ] 3.2 `uv run ruff check src tests` and `uv run basedpyright src tests` are clean in `python/`

## 4. npm twin

- [ ] 4.1 `node/src/refactor/compliance.ts` passes `any` / `top` from the TypeScript language facts; TypeScript
      goldens unchanged; `npm run lint && npm run typecheck` and the node contract test pass

## 5. Docs

- [ ] 5.1 `docs/deterministic-refactoring.md`: the Python checks row adds `explicit-any`
- [ ] 5.2 `plugin/languages/python.md`: add the approved fix line (design.md decision 5) after `unannotated-attr`

## 6. Gates

- [ ] 6.1 The local test scope (`la-affected-tests` plus the conformance cases and contract tests reached) passes in
      both twins; `scripts/conformance-cross` for the new and changed cases passes
- [ ] 6.2 Enforcement bundle green: `la-arch-check`, LikeC4 validation, `la-typecheck` against its baseline
