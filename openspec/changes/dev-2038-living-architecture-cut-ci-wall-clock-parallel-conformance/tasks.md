## 1. Failing tests (pr-tests stage)

- [ ] 1.1 Serial update mode (design D1): a Python test runs `pytest -n 4 tests/test_conformance.py::test_corpus_is_not_empty` in a subprocess with `LA_UPDATE_GOLDENS=1` and asserts that no xdist worker starts; the same run without update mode does start workers. Writes no goldens. Fails until the conftest hook exists.
- [ ] 1.2 `scripts/conformance-cross` argument validation (design D2): a Python test asserts that `--twin` with no value and `--twin nope` each exit 2 with a usage line on stderr and do not build `node/`.
- [ ] 1.3 Lazy TypeScript (design D3), in `node/test/packaging.test.ts` against the installed package: a CommonJS preload through `NODE_OPTIONS=--require` writes a marker at exit when a module under `node_modules/typescript/` was loaded. Negative: installed `la-config --help` leaves no marker. Positive control: installed `la-arch-check` on a TypeScript fixture (a conformance case repo) exits as its golden says and leaves the marker.
- [ ] 1.4 npm self-skip (design D4), in `packaging.test.ts`: installed `la-check-conventions` with `PATH` = `<prefix>/bin`, then a stub Python-twin dir (`la-doctor --twin` prints the qualifying line, the stub command logs itself). The preload logs every node process's script: the own `la-doctor.js` never runs, the stub `la-doctor` and command do, and the exit code is the stub's.
- [ ] 1.5 npm fallback (design D4): when the running entry point has no resolvable sibling `la-doctor`, discovery skips nothing and still selects the first qualifying directory (Vitest; the entry point and spawns are controlled by the test, not Vitest's argv).
- [ ] 1.6 PyPI self-skip (design D4): with `sys.argv[0]` set to the venv's real `la-arch-check` console script and `PATH` = the venv bin dir, then a stub TypeScript-twin dir, recorded `la-doctor` spawns exclude the venv's own and discovery returns the stub dir. Fallback: `sys.argv[0]` without a sibling `la-doctor`, or with an unresolvable one, skips nothing and the first qualifying directory is still selected.
- [ ] 1.7 Codex review of the tests against the plan (pr-tests Step 2). Verify that the findings are resolved with the user.

## 2. Parallel runs

- [ ] 2.1 Add `pytest-xdist` to `python/` dev dependencies (`uv add --dev`, updating `uv.lock`) and `addopts = "-n auto"`. Verify `uv sync --locked` and that `uv run pytest -q` reports xdist workers.
- [ ] 2.2 `python/tests/conftest.py`: a `pytest_configure` hook that, under `LA_UPDATE_GOLDENS=1`, sets `numprocesses=0`, `dist="no"` and `tx=[]` (design D1). Verify test 1.1.
- [ ] 2.3 Race check: run the full Python suite and both `scripts/conformance-cross --twin <twin>` legs under `-n auto` at least 5 times each. Verify that every run is green with an identical pass count.

## 3. Cross-twin script

- [ ] 3.1 `scripts/conformance-cross`: optional leading `--twin <python|typescript>`; a missing or unknown value exits 2 with usage before building; without `--twin`, both twins run as today; remaining args go to pytest. Verify test 1.2 and one local run per twin.

## 4. Lazy TypeScript (npm twin)

- [ ] 4.1 `node/src/lang/ts.ts` with the cached `ts()` accessor; switch `imports.ts`, `projects.ts` and `specifiers.ts` to `ts()` and `import type * as TS`. Verify tests 1.3, `npm run lint`, `npm run typecheck`, and `la-config --help` ≤ 0.1 s locally.

## 5. Discovery self-skip (both twins)

- [ ] 5.1 PyPI twin `_discover_dir`: resolve the own `la-doctor` (design D4) and skip a candidate whose `la-doctor` real path equals it. Verify test 1.6.
- [ ] 5.2 npm twin `discoverDir`: the same logic. Verify tests 1.4 and 1.5.

## 6. CI and docs

- [ ] 6.1 `.github/workflows/ci.yml`: `cross-twin` matrix over `twin: [python, typescript]` (`fail-fast: false`) calling `scripts/conformance-cross --twin ${{ matrix.twin }}`; `node` job without `npm run conformance`, `setup-uv`, `uv sync` and the separate build; `cache: npm` with `cache-dependency-path: node/package-lock.json` in `node` and `cross-twin`. Verify with `actionlint` (or a careful read) and the PR's CI run.
- [ ] 6.2 AGENTS.md and `conformance/README.md`: `scripts/conformance-cross [--twin <twin>]`, the parallel default, `-n 0` for debugging, and the D1 rule that tests never write shared paths. Verify that the scrub and skills tests pass.
- [x] 6.3 `plugin/skills/pr-plan/SKILL.md`: the "Recommendation bias" paragraph says to ask only about genuine choices and never to offer an option whose only pro is a smaller diff (user request during planning).

## 7. Verification

- [ ] 7.1 Full Python suite, `npm run lint && npm run typecheck && npm test`, and `scripts/conformance-cross` all green with no golden change (`git status conformance/` clean).
- [ ] 7.2 On the PR: every check passes and the slowest job takes ≤ 5 min. Record before (run 37117736893) and after times per job in the PR description.
