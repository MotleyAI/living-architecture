## Context

See proposal.md for motivation. Measured locally on `main` @ `f450906` (32 cores; GitHub's public `ubuntu-latest`
has 4 vCPU and ran about 1.6× slower than local):

| run | serial | `-n 4` | `-n auto` |
| -- | -- | -- | -- |
| Python suite (2,482 tests) | 87.8 s | 29.4 s | 10.0 s |
| cross-twin through the PyPI twin (472 cases) | 107 s | 37.9 s | |
| cross-twin through the npm twin (472 cases) | 274 s | 96.6 s | |

npm-twin start: 0.25 s, of which `import('typescript')` is 0.19 s; the contract alone loads in 0.05 s. CI
before: run 37117736893, `cross-twin` 10m36s, `test` 2m08s–2m57s, `node` 2m41s.

Principles (system.arc42.md): P1 twins identical (the self-skip is the same in both twins; no golden moves),
P2 contract only (no new texts or parameters), P3 language-specific code only in `lang`/`refactor` (the lazy
compiler accessor lives in `node/src/lang`). No capability is added; no `index.yaml`, model or arc42 change.

## Goals / Non-Goals

**Goals:** slowest CI job ≤ 5 min; npm-twin `la-config --help` ≤ 0.1 s locally; no observable behaviour change.

**Non-Goals:** pruning or auditing the corpus; skipping in `cross-twin` the cases a twin's own suite already runs
(each leg still runs every case, so the shared-contract cross-twin requirement holds as written); Python
start-up time; reducing the Python version matrix.

## Decisions

### D1. `-n auto` as the pytest default; update mode forced serial

`addopts = "-n auto"` in `python/pyproject.toml` serves CI, `scripts/conformance-cross`, `npm run conformance`
and a local `uv run pytest -q` alike. Alternative: explicit `-n auto` in CI and the two scripts only. Rejected:
three places to keep in sync and a slow default local run. Debugging uses `-n 0`.

Update mode (`LA_UPDATE_GOLDENS=1`) must write goldens from one process. xdist's tryfirst `pytest_cmdline_main`
has already turned `-n` into `numprocesses`, `dist=load` and `tx=[popen…]` before any conftest hook runs, and its
trylast `pytest_configure` creates the worker session only if `dist != "no"` and `tx` is non-empty. So a
`pytest_configure` hook in `python/tests/conftest.py` resets `numprocesses=0`, `dist="no"` and `tx=[]` when
update mode is on, even when `-n` is passed explicitly. Resetting `numprocesses` alone is not enough.

Why the corpus is safe under xdist: `_TOOLS_DIRS` is per process, and each worker makes its own `mkdtemp` tools
dir and registers only that dir with its own `atexit`; `tmp_path` is per worker; the committed corpus is
read-only outside update mode. Rule for all tests from now on: a test never writes to a shared checkout path or
a fixed external path; it writes under its own temporary directory.

### D2. `cross-twin` as a matrix over the invoking twin

`scripts/conformance-cross [--twin <python|typescript>] [pytest args...]`: a leading `--twin` selects one twin,
without it both run as today. A missing or unknown `--twin` value exits 2 with a usage line before building.
CI runs one leg per twin, `fail-fast: false`, each calling the script, so local and CI runs are the same
command. The script builds `node/` once per invocation.

### D3. Lazy TypeScript via a synchronous accessor in `lang`

`node/src/lang/ts.ts` exports `ts()`, which on first call loads the compiler with
`createRequire(import.meta.url)('typescript')` and caches it. `typescript` is CommonJS, so `require` returns the
same module object as today's default import. `imports.ts`, `projects.ts` and `specifiers.ts` call `ts()`;
type positions use `import type * as TS from 'typescript'`, erased at compile time. `dispatch` and
`archcheck.run` stay synchronous; nothing outside `lang` changes.

Alternatives: `await import('typescript')` makes the facts path async up through `archcheck.run`, `dispatch`
and `main` for no extra speed. Lazy per-command handler loading in `cli` saves about 0–10 ms on top (measured),
not worth async dispatch.

Observation in tests: a CommonJS preload passed through `NODE_OPTIONS=--require=<probe.cjs>` writes a marker at
process exit when any loaded module's path lies under `node_modules/typescript/`. It runs against the packed,
installed package (`node/test/packaging.test.ts`), which also proves `createRequire` resolves `typescript` from
the installed package, not the checkout.

### D4. Discovery skips the invoking twin's own `la-doctor`

"Own `la-doctor`" is the sibling of the running entry point, resolved to its real path:

- PyPI twin: `(Path(sys.argv[0]).resolve().parent / "la-doctor").resolve(strict=True)`. For a console script,
  `sys.argv[0]` is the invoked script path.
- npm twin: `realpathSync(join(dirname(realpathSync(process.argv[1])), 'la-doctor.js'))`. An npm bin is a
  symlink to `dist/bin/<command>.js`, whose sibling is `la-doctor.js`.

If the sibling is missing, unresolvable or not a file, nothing is skipped (today's behaviour). A candidate is
skipped when `realpath(<dir>/la-doctor)` equals the own path; the per-directory real-path dedup stays separate,
and the order and first-qualifying selection are unchanged. Comparing file real paths, not directories, covers
npm global bins (`<prefix>/bin/la-doctor` → `…/dist/bin/la-doctor.js`), pipx/uv tool shims and the conformance
runner's symlink dir. A second, separate install of the same twin elsewhere on `PATH` is still probed, which is
harmless.

Tests use real entry-point paths, never the test runner's own argv:

- npm: end-to-end in `packaging.test.ts`. The installed `<prefix>/bin/la-check-conventions` forwards, with
  `PATH` holding `<prefix>/bin` and then a stub Python-twin dir. The `NODE_OPTIONS` preload logs every node
  process's script; the own `la-doctor.js` never runs, and the stub's `la-doctor` and command do.
- PyPI: in-process, because the PyPI twin forwards only facts requests and stubbing a valid facts document is
  heavy. `sys.argv[0]` is set to the venv's real `la-arch-check` console script, and `la-doctor` spawns are
  recorded.
- Both twins pin the fallback: if the own `la-doctor` is missing or unresolvable, nothing is skipped and the first
  qualifying directory is still selected.

### D5. CI duplication and caching

The `node` job drops `npm run conformance` (the `cross-twin` typescript leg runs a superset), `setup-uv` and
`uv sync` (only conformance needed them), and its separate `npm run build` (`packaging.test.ts` builds in
`beforeAll`). It keeps `sync-shared --check` (system `python3`), `npm ci`, lint, typecheck and Vitest.
`actions/setup-node` gets `cache: npm` with `cache-dependency-path: node/package-lock.json` in the `node` and
`cross-twin` jobs. `setup-uv` caching is already on by default for GitHub-hosted runners.

## Risks / Trade-offs

- [A future test writes shared state and races under xdist] → the D1 rule, and the full suite runs on three
  Python versions in CI.
- [`-n auto` worker start-up on a single-test run, `pdb`/`-s` under xdist] → `-n 0` (xdist already disables
  itself for `--pdb`).
- [`createRequire` resolves a different `typescript` than the static import did] → the packed-install positive
  test, plus the whole TypeScript-adapter corpus through the npm twin.
- [The self-skip misidentifies a qualifying twin as our own] → impossible by construction (a real-path-equal
  file is our own entry), and the conformance forwarding cases stay byte-identical.
