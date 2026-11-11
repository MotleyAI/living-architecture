## Why

Since pyright 1.1.364 (microsoft/pyright#11919, still in basedpyright 1.40.2; the fix PR #11923 is open), a loop
like `for k in …: assert k in d, k` can leave an incomplete type for `d` in pyright's code-flow cache, and the
checker silently drops diagnostics on it. Whether a later evaluation repairs the entry depends on what the process
checked first, so `la-typecheck` results depend on file order, `--threads` and CPU count, and CI can disagree with
a local run. Storyline patches its own venv with a wrapper (DEV-2140); every la repo needs the same fix, once.

## What Changes

- `la-typecheck`'s Python run loads a Node preload shipped in the PyPI twin through the checker's
  `NODE_OPTIONS` (appended to any existing value). The preload removes the buggy condition from basedpyright's
  `dist/pyright.js` in memory as Node compiles it; no file of the target repo or its environment changes.
- The preload patches only a basedpyright version listed in a verified-version table in the shared contract
  (initially `1.40.2`) whose bundle contains the patched line exactly once; otherwise the run exits 2.
- A Python run where the patch provably did not apply (no preload result) exits 2: the configured command must
  run basedpyright under Node and keep `NODE_OPTIONS`.
- Three new user-facing texts (`typecheck.patch-not-applied`, `typecheck.patch-unverified`,
  `typecheck.patch-mismatch`), the `commands.typecheck.python` schema description and the docs say so.
- **BREAKING** for repos whose basedpyright is not a verified version, or whose Python command does not run
  basedpyright under Node: `la-typecheck` exits 2 until they pin a verified version.
- This repo pins `basedpyright==1.40.2` (dev group and the `verify` extra).
- Threads, heap and all other checker options stay in the configured command.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `typecheck`: the Python run applies the pyright#11919 patch and fails when it cannot; basedpyright's output
  and exit codes pass through only for a patched run.

## Impact

- Code: `python/src/living_architecture/lang/` (patch environment, result reading, the preload `.cjs` as package
  data), `python/src/living_architecture/typecheck/` (wiring around the Python run). No npm twin code: it relays
  the Python section from the PyPI twin unchanged.
- Contract: `shared/languages.yaml` (verified-version table), `shared/findings.yaml` (three texts),
  `shared/schema/living-architecture.schema.json` (command description); vendored snapshots via
  `scripts/sync-shared`.
- Tests: every conformance case that runs a Python fake checker, new conformance cases, Python unit tests,
  integration tests with real basedpyright 1.40.2, a wheel-content test.
- Docs: `docs/ci.md`, `docs/configuration.md`, `docs/commands.md`, `plugin/languages/python.md`.
- Dependencies: `basedpyright==1.40.2` in `python/pyproject.toml` (dev group, `verify` extra) and `uv.lock`.
- Downstream: storyline can replace its wrapper with plain basedpyright once an la release carries this.
