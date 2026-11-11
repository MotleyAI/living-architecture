## 0. Calibration (read before tests and code)

- The la ↔ preload protocol (internal to `python.lang`; conformance fakes simulate it):
  - `LA_PYRIGHT_PATCH_RESULT`: absolute path of the result file, in a temp dir la creates and removes.
  - `LA_PYRIGHT_PATCH_VERSIONS`: the verified table as a JSON list of strings.
  - Result file: one JSON object `{"outcome": "patched" | "unverified" | "mismatch", "version": "<embedded
    basedpyright version>", "count": <occurrences of the condition>}`, written only by the main thread.
  - `NODE_OPTIONS` for the child: the inherited value, a space, then `--require "<absolute preload path>"`
    (double-quoted; just the `--require` part when nothing was inherited).
- `{verified}` in `typecheck.patch-unverified` is the table joined with `, `. `{command}` in
  `typecheck.patch-not-applied` is the configured command string, as in `typecheck.header`.
- Precedence after the run: result `unverified` / `mismatch` → that text, exit 2; no result file → not-applied
  text, exit 2; `patched` → today's exit mapping. The patch texts print after the command's relayed output.
- The embedded version is the string exported by the bundle module `"../pyright-internal/src/version.json"`;
  basedpyright's `package.json` holds pyright's version and must not be used.
- The preload acts only on a `dist/pyright.js` whose bundle defines that version module; any other compiled file
  is untouched. Wrap `Module.prototype._compile`; use `require('worker_threads').isMainThread` to pick the writer;
  write the result synchronously to a temp file in the same directory, then rename, before `process.exit(2)`.
- Every fake Python checker in the corpus must, before writing `{"outcome": "patched", …}`, assert that
  `NODE_OPTIONS` ends with `--require "<…>/<preload file name>"`, and that both variables are set. Inventory:
  `grep -rl basedpyright conformance` (the `.venv/bin/basedpyright` fakes in `typecheck-python-*`,
  `typecheck-mixed-*`, `twin-typecheck-forwarded-typescript`, `twin-typecheck-unavailable`, plus fakes declared
  under `bins:` in `case.yaml`).

## 1. Shared contract

- [x] 1.1 Add the python fact `checker_patch_versions: ['1.40.2']` to `shared/languages.yaml` and document it in the
      header comment; add the three approved texts (design.md decision 17, verbatim) to `shared/findings.yaml`;
      extend the `commands.typecheck.python` description in `shared/schema/living-architecture.schema.json` (must
      run a verified basedpyright under Node and keep `NODE_OPTIONS`); run `scripts/sync-shared`; verify
      `scripts/sync-shared --check` passes and `test_contract.py` / `test_sync_shared.py` pass.

## 2. Tests (pr-tests stage)

- [x] 2.1 Unit tests in `python/tests/test_typecheck.py` (or a new `test_pyright_patch.py`): child environment
      (appends to an inherited `NODE_OPTIONS`, quotes a preload path with spaces, sets both variables), result
      reading and the exit precedence above, write mode writes no baseline on a patch failure.
- [x] 2.2 Preload tests run under `nodejs_wheel`'s Node against fake bundle directories (`<pkg>/dist/pyright.js`
      requiring nothing, defining the version module): verified + once → patched (the compiled code sees the
      condition replaced, the file on disk is unchanged); unlisted version (1.39.10) → `unverified`, Node exits
      non-zero; count 0 and 2 → `mismatch`; a `pyright.js` without the version module and an unrelated file → no
      result; a worker thread compiling the bundle is patched and writes nothing.
- [x] 2.3 Wheel test in `python/tests/test_packaging.py`: the built wheel contains the preload, and the installed
      package locates it.
- [x] 2.4 Conformance: update every fake Python checker per the calibration note; add cases for not-applied,
      unverified, mismatch (with checker output relayed first), patched with new errors (exit 1), write mode
      refused on unverified (no baseline written), a preset `NODE_OPTIONS` kept first, and a mixed-repo patch
      failure run through both twins; list them in `conformance/INVENTORY.md`; each new findings text has a golden.
- [x] 2.5 Integration tests in `python/tests/integration/test_typecheck_real.py` with the real basedpyright
      1.40.2: the minimal repro (`for k in ["a"]: assert k in d, k` then `x: str = d["a"]` with
      `d: dict[str, int]`) reports its error and exits 1; 13 copies with `--threads 4` in the command report 13
      errors; a wrapper command (a script in the temp repo that execs the venv's basedpyright) is patched; every
      file under the installed `basedpyright` package is byte-identical after the run.

## 3. Implementation

- [ ] 3.1 Add the preload `.cjs` to `python/src/living_architecture/lang/` as package data, with a forward-pointer
      comment to microsoft/pyright#11919 for its removal; verify 2.2 and 2.3 pass.
- [ ] 3.2 Add the patch environment and result reading to `lang/typecheck.py`, export them from `lang`, and wire
      them into `_run_python` in `typecheck/__init__.py`; verify 2.1 and 2.4 pass, and the integration tests 2.5
      pass with `uv run pytest -m integration`.
- [ ] 3.3 Pin `basedpyright==1.40.2` in `python/pyproject.toml` (dev group and the `verify` extra), refresh
      `python/uv.lock` with `uv lock`; verify `uv run basedpyright --version` reports 1.40.2 and
      `la-typecheck` passes on this repo.
- [ ] 3.4 Update `docs/ci.md`, `docs/configuration.md`, `docs/commands.md` and `plugin/languages/python.md`:
      pin basedpyright to a verified version; la applies the pyright#11919 patch in memory; the command must run
      basedpyright under Node and keep `NODE_OPTIONS`; verify `test_skills.py` and `test_how_it_works.py` pass.

## 4. Verification

- [ ] 4.1 Python twin: `uv run pytest -q`, `uv run ruff check src tests`, `uv run basedpyright src tests`; npm
      twin: `npm run lint && npm run typecheck`, `npm test`, `npm run build && npm run conformance`;
      `scripts/conformance-cross`; `scripts/sync-shared --check`.
- [ ] 4.2 Enforcement bundle: `la-arch-check`, `npx likec4 validate architecture`, `la-typecheck` all green.
