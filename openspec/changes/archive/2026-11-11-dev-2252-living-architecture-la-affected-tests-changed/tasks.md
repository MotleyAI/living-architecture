## 1. Shared contract

- [x] 1.1 Add `la-affected-tests` to `shared/cli.yaml` (neutral; `--base` string, internal `--language {python,typescript}`, `require_one_of: [base, language]`, exit `{0: ok, 2: 'usage, config or git error, other twin unreachable, or format refusal'}`); verify both twins' parser tests list the command
- [x] 1.2 In `shared/findings.yaml`: move `conventions.pr-base-unresolved` and `conventions.git-failed` to `changes.*` with identical text; add `affected.error` and the unrepresentable-path text; verify `la-check-conventions` goldens are byte-identical
- [x] 1.3 Add the shared schema(s) for the internal request (changed paths with a deleted flag; repo-relative POSIX, no absolute/`.`/`..`/backslash segments) and response (`language`, `version`, `contract_hash`, `tests`); verify schema unit tests in both twins
- [x] 1.4 Add `imports_non_source` to every language in `shared/languages.yaml` (typescript true, python false) and to its header comment (design.md decision 27); verify the languages-registry tests in both twins
- [x] 1.5 Run `scripts/sync-shared`; verify `scripts/sync-shared --check` and the drift tests pass

## 2. Architecture harness

- [x] 2.1 Apply the approved `architecture/model.c4` edit verbatim (design.md, Structure) in both roots; run `la-arch-diagrams`; verify `la-arch-check` and LikeC4 validation pass once the packages exist (any arrow mismatch goes back to the user before changing the model)

## 3. Change set (`changes` node) and test-file classification

- [x] 3.1 Python: create `living_architecture.changes` with base-ref resolution and the NUL-delimited, `--no-renames` change listing (with/without deletions and untracked); switch `conventions.gate` to it; verify conventions tests and goldens unchanged
- [x] 3.2 npm: the same under `node/src/changes`, `node/src/conventions/gate.ts` switched; verify Vitest + `npm run conformance` unchanged for conventions cases
- [x] 3.3 Move `is_test_file`/`isTestFile` into `contract` in both twins and update callers; verify the test-file classification vectors pass

## 4. Language adapters (`lang`)

- [x] 4.1 Python `lang`: `ast` all-imports scan (incl. `TYPE_CHECKING`) + lexical scan (continuations, parenthesized multi-line, star, aliases), unioned; verify unit tests incl. a file the interpreter cannot parse
- [x] 4.2 Python `lang`: file resolution (dotted-suffix match over graph files, parent `__init__.py`s, `from a.b import c` → `a.b.c`, relative levels probing names and the package `__init__.py`, own package chain, deleted paths) returning repo-relative edges; verify unit tests: several roots with the same `a/b.py`, module/package collision, namespace dirs, `__init__` importers with `from . import x` / `from .. import y`, excessive levels, imports inside functions/classes
- [x] 4.3 npm `lang`: all-specifiers scan (static/dynamic imports and exports, `import x = require()`, literal `require()`, type-only forms, `ImportTypeNode`, `/// <reference path>`) beside the unchanged `runtimeSpecifiers`; verify unit tests per construct and that arch-check tests are unchanged
- [x] 4.4 npm `lang`: per-file nearest-tsconfig project cache, virtual host for deleted paths (`fileExists`, ancestor `directoryExists`, identity `realpath`), edge-target mapping (in-repo, outside `node_modules`, real path through `node_modules`), extension-candidate fallback for unresolved relative specifiers; verify unit tests: `paths` alias, `baseUrl`, project references, nested configs with different `paths`, a test excluded from its tsconfig, NodeNext `.js`→`.ts`, JSX, JSON module, deleted target behind an alias, deleted directory index, symlinked workspace package

## 5. The command (`affected` node)

- [x] 5.1 Python `affected`: changed set, path policy (non-UTF-8 / CR / LF → exit 2 naming the path), per-language routing, reverse BFS from every changed/deleted file, `test_globs` filter, internal `--language` mode (JSON in/out), union + code-point sort, stdout only on success; wire into `cli`; verify unit tests (direct, transitive, cycle, changed helper, type-only edge, untouched test absent, deleted test not printed)
- [x] 5.2 npm `affected`: the same; wire into `node/src/cli`; verify Vitest
- [x] 5.3 Twin request: call the other twin through `twin` with identity + schema checks, never probing an untouched language; verify twin unit tests in both twins (unreachable → exit 2 with hint and empty stdout; failing response → exit 2)

## 6. Conformance

- [x] 6.1 Add git-scripted cases (paired `python/`/`node/` overlays where the language matters): changed test only; transitive reach with an unrelated test absent; changed test helper; type-only edge; deleted module still imported; rename; deleted test; untracked new test; ignored untracked file; staged-only and unstaged-only edits; nested cwd; no changes → empty/0; YAML-only change → empty; repo without `architecture/`; spaces/non-ASCII with `core.quotePath` true and code-point order; newline path → 2; missing base ref → 2; base branch name with `/`; not a git repo → 2; unborn HEAD → 2; two-language union through either twin; other twin unreachable → 2; Python file the interpreter cannot parse; TS path alias, JSON module, deleted directory index
- [x] 6.2 List every case in `conformance/INVENTORY.md`; verify every new `findings.yaml` template is produced by a golden, `uv run pytest -q` in `python/`, `npm run build && npm run conformance` in `node/`, and `scripts/conformance-cross` pass

## 7. OpenSpec mapping

- [x] 7.1 Verify `la-arch-check` maps the `affected-tests` spec group exactly once (via `python.affected` `specs`) and `openspec validate dev-2252-living-architecture-la-affected-tests-changed --strict` passes

## 8. Skills and docs

- [x] 8.1 Apply the Part B wording verbatim (design.md decisions 6 and 7) to `plugin/skills/pr`, `pr-tests`, `pr-implement`, `pr-review` and `docs/how-it-works.md`; verify skill tests (`python/tests/test_skills.py`, `node/test/skills.test.ts`) and `npx -y @anthropic-ai/claude-code plugin validate plugin`
- [x] 8.2 `docs/commands.md`: the command row and a short section (surface, selection, what it leaves to the agent); verify any docs tests pass

## 9. Final gates

- [x] 9.1 Full suites green: `uv run pytest -q`, `uv run ruff check src tests`, `uv run basedpyright src tests` in `python/`; `npm run lint && npm run typecheck && npm test` and `npm run build && npm run conformance` in `node/`; `scripts/conformance-cross`
- [x] 9.2 Enforcement bundle green: `la-arch-check`, LikeC4 validation, `la-typecheck`, `la-check-conventions --base main`
