## 0. Stage order (read first)

- [x] 0.1 pr-tests writes section 1 only; pr-implement does sections 2–6. While section 1 is open the stage is
      `pr-tests`. Before opening the PR, check DEV-2301's state: merge its branch
      (`egor/dev-2301-living-architecture-dr-refactor-resolves-every`) or, once merged, `origin/main` into this branch
      (`git merge <ref> -m "Merge branch '<ref>' into …"`; never rebase or stash) and re-run the local test scope.
      This PR merges only after DEV-2301.
- [x] 0.2 No golden changes anywhere in this change. A conformance diff is a bug in the change, never a golden to
      regenerate.

## 1. Tests (pr-tests)

- [x] 1.1 `python/tests/test_pyright_export.py`: an export over a project whose model subclasses
      `pydantic.BaseModel` returns no `followed` fact located in a third-party or typeshed file (design 8). Verify:
      fails today.
- [x] 1.2 Same file: a first-party chain (class → field annotation → class → field annotation) is still followed to
      its end, and a direct `definition` request landing in pydantic or typeshed is still answered (design 8).
      Verify: passes today and after A.
- [x] 1.3 A partition test for the CI split (design 12): for each job kind (Python suite with the conformance cases
      deselected; cross-python; cross-typescript, each under its real `LA_CONFORMANCE_*` environment and bin dirs),
      collecting with `--splits <n> --group <g>` for every group gives every collected node id exactly once.
      Verify: fails today (no `pytest-split`, no duration files).
- [x] 1.4 The CI workflow test (structural, no wording): `test` is a matrix of the four Python versions × 2 shards
      passing `--splits 2 --group <shard>` and the conformance deselection; ruff, basedpyright and
      `sync-shared --check` run only in shard 1; `cross-twin` is twin × 3 shards passing `--splits 3 --group <shard>`.
      Verify: fails today.
- [x] 1.5 Import test (design 15): each lightweight command (`la-config`, `la-doctor` with `--twin` and
      `--contract-hash`, every review shim) run in a subprocess loads none of `rope`, `living_architecture.refactor`,
      `.archcheck`, `.c4`, `.conventions`, `.typecheck`, `.affected`. Verify: fails today.
- [x] 1.6 Every `[project.scripts]` entry points to `living_architecture.cli.<command_snake>:<command_snake>`, and
      `cli/__init__.py` imports no command package (structural test). Verify: fails today.

## 2. A — export follow

- [x] 2.1 `Exporter.follow` returns early when the location's `SourceFileInfo` is missing, `isThirdPartyImport` or
      `isTypeshedFile` (design 7). Verify: 1.1 and 1.2 pass; the refactor, compliance and keyed tests and the Python
      conformance cases pass with no golden change.

## 3. C — one entry module per command

- [x] 3.1 Move each entry point to `living_architecture/cli/<command_snake>.py` with `la:deterministic-refactor`
      (`dr-refactor` dry-run → review → `--apply`, then its gate); `cli/__init__.py` keeps only `_run`, `_root`,
      `_checked_root`, `_argv`. Repoint `[project.scripts]`; update every test importing from
      `living_architecture.cli`. Verify: 1.5 and 1.6 pass; `la-arch-check` green (measured edges unchanged);
      conformance green.

## 4. B, D — CI

- [x] 4.1 Add `pytest-split` to `python/` dev dependencies (`uv.lock`). Verify: `uv sync --locked` succeeds.
- [x] 4.2 `ci.yml`: `test` = version × 2 shards with `--splits 2 --group <shard>
      --durations-path <suite file> --deselect tests/test_conformance.py::test_case`, ruff, basedpyright and
      `sync-shared --check` in shard 1 only; `cross-twin` = twin × 3 shards, `scripts/conformance-cross --twin <twin>
      --splits 3 --group <shard> --durations-path <twin file>`. Verify: 1.4 passes.
- [x] 4.3 Record the duration files with `--store-durations` in a temporary CI step on this branch (one per job kind,
      design 11), commit them, then remove the temporary step. Verify: 1.3 passes; the temporary step is gone
      (`git diff origin/main -- .github` shows only 4.2's changes).
- [x] 4.4 `docs/development.md`: how to refresh the duration files. Verify: the doc names the command and the three
      files.

## 5. Profile

- [x] 5.1 Fill profile.md's "After" table from the PR's CI run: wall-clock and summed test time per job kind, against
      the "Before" rows. Verify: every heavy job kind has both rows.

## 6. Gate

- [x] 6.1 Enforcement bundle: `la-arch-check`, `npx likec4 validate architecture`, `la-typecheck`; ruff; the local test
      scope. Verify: all green.
