## Why

Since the npm twin landed (DEV-2025), every push waits on the `cross-twin` CI job, which runs every conformance
case serially through both twins: 10m36s on `main`'s last run and up to 16m41s on PR #4, while every other job
finishes in 2–3 min. Most of that cost is avoidable: the corpus runs serially, every npm-twin process loads the
TypeScript compiler (0.19 s of its 0.25 s start), forwarding probes the invoking twin's own `la-doctor`, and the
`node` job repeats the npm twin's native corpus that `cross-twin` already runs.

## What Changes

- **Parallel test runs**: `pytest-xdist` becomes a Python dev dependency and `-n auto` the pytest default, so the
  Python suite, `scripts/conformance-cross` and `npm run conformance` run in parallel. The golden update mode
  (`LA_UPDATE_GOLDENS=1`) always runs serially.
- **`cross-twin` split**: a CI matrix over the invoking twin (`python`, `typescript`); `scripts/conformance-cross`
  gains an optional `--twin <python|typescript>` and still runs both twins without it. Each leg still runs every
  case through its twin.
- **Lazy TypeScript in the npm twin**: the compiler loads on first use inside `lang`, so commands that never
  measure TypeScript edges (`la-config`, `la-doctor`, forwarded commands, …) start without it.
- **Discovery skips the invoking twin's own `la-doctor`** (both twins): that probe can never qualify, so skipping
  it saves one process start per forwarded call and per facts request without changing which twin is found.
- **No duplicated runs**: the `node` job drops its native conformance run, its `uv` setup and its separate build
  (the packaging test builds); the Python matrix keeps 3.11–3.13. npm caching in CI.
- Docs: AGENTS.md and `conformance/README.md` describe `--twin`, the parallel default and `-n 0` for debugging.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `twin-forwarding`: "The other twin is found by identity" also skips the directory whose `la-doctor` is the
  invoking twin's own.

## Impact

- `python/`: `pyproject.toml` (dev dependency, `addopts`), `uv.lock`, `tests/conftest.py` (serial update mode),
  `src/living_architecture/twin/__init__.py` (self-skip), tests.
- `node/`: `src/lang/` (lazy compiler accessor; `imports.ts`, `projects.ts`, `specifiers.ts`),
  `src/twin/index.ts` (self-skip), `test/packaging.test.ts` and twin tests.
- `scripts/conformance-cross`, `.github/workflows/ci.yml`, AGENTS.md, `conformance/README.md`.
- No golden, shared-contract, `architecture/` or version change. Observable command output is unchanged.
