## Why

With DEV-2301 merged in, CI's heavy jobs take 13–21 min per push (about 11 min on `main` before it). The profile
(`profile.md`) shows where the time goes: GitHub's 4-vCPU runners alone explain the gap to a local run, DEV-2301's
export pass follows definitions into library stubs, every Python-twin process imports every command's package, the
conformance corpus runs in all four `test` jobs as well as in `cross-twin`, and each heavy job runs serially on one
runner. This change measures that and cuts it.

## What Changes

- **Export follow stays in user code**: the basedpyright export pass (`lang/pyright_export.cjs`) no longer follows a
  definition into a third-party or typeshed file. The private export protocol between la and its patched
  basedpyright changes (fewer `followed` facts); command output does not.
- **Sharded CI**: `test` runs as Python version × 2 shards and `cross-twin` as twin × 3 shards, split by committed
  `pytest-split` duration files; ruff, basedpyright and `sync-shared --check` run in shard 1 only.
- **One entry module per Python-twin command**: `living_architecture/cli/<command>.py` imports only what that
  command needs; `cli/__init__.py` keeps only the shared dispatch helpers.
- **Conformance runs once**: the `test` jobs deselect the conformance cases (`test_conformance.py::test_case`);
  `cross-twin` runs every case, on Python 3.13. Local `uv run pytest -q` is unchanged.
- **Profile**: `profile.md` in this change records the measurements, the ranked options with expected and measured
  savings, the cross-check of DEV-2038's list, and CI times per job before and after.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

None. No specified behaviour changes (`skip_specs: true`): commands, flags, output and exit codes stay identical,
and the cross-twin run still runs every case through each twin's entry points (the union of its shards).

## Impact

- `python/src/living_architecture/lang/pyright_export.cjs` (`python.lang`).
- `python/src/living_architecture/cli/` and `python/pyproject.toml` `[project.scripts]` (`python.cli`); every test
  importing a command from `living_architecture.cli`.
- `.github/workflows/ci.yml`, `scripts/conformance-cross`, `python/pyproject.toml` dev dependencies (`pytest-split`)
  and `uv.lock`, new committed duration files, `docs/development.md` (duration refresh).
- Coverage: conformance no longer runs on Python 3.11, 3.12 and 3.14 in CI (approved).
- Depends on DEV-2301 (merged into this branch); this PR merges after it.
