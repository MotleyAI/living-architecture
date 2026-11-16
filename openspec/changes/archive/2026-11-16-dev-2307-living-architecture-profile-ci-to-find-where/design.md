## Context

See proposal.md (Why) and profile.md (the measurements). Today:

- `.github/workflows/ci.yml`: `test` (Python 3.11–3.14: `sync-shared --check`, `uv sync`, ruff, basedpyright,
  `uv run pytest -q`, which includes the twin-native conformance cases), `package`, `node`, `cross-twin` (matrix over
  the invoking twin: `scripts/conformance-cross --twin <twin>`, Python 3.13), `acceptance-node-only`, `plugin`.
  `pytest` runs with `-n auto` (`python/pyproject.toml` `addopts`).
- `scripts/conformance-cross` builds the npm twin and runs `npm run conformance -- <pytest args>` with
  `LA_CONFORMANCE_CROSS=1 LA_CONFORMANCE_TWIN=<twin>`; `node/scripts/conformance.mjs` runs
  `uv run pytest -q tests/test_conformance.py <args>` in `python/`.
- `living_architecture/cli/__init__.py` holds all 19 entry points and imports `affected`, `archcheck`, `c4`,
  `config`, `conventions`, `doctor`, `refactor`, `review`, `twin` and `typecheck` at the top, so every command pays
  for all of them (rope, jsonschema, the refactor package).
- `lang/pyright_export.cjs` (DEV-2301): `Exporter.follow` adds definition facts transitively from a class (bases,
  field annotations), function (decorators, parameter annotations) or parameter, wherever the definition lands.

Principles that apply (`architecture/system.arc42.md`; `python.cli` and `python.lang` have no arc42 of their own):
1. Twins — no observable behaviour changes; the conformance corpus stays green with no golden changes, run through
   both twins in `cross-twin`.
2. Parameters and texts only from the shared contract — the per-command modules keep reading the manifest through
   the shared `_run`; nothing is hard-coded.
3. Language-specific code only in `lang` and `refactor` — the follow guard stays in `lang`.
4. Tools never execute target-repo code — unchanged.

No model or arc42 edit: the module split stays inside `python.cli`, and the measured edges from `python.cli` are the
same set the model already declares.

## Goals / Non-Goals

**Goals:** cut CI wall-clock per push with no change to command behaviour and no golden change; record the profile
and the before/after times.

**Non-Goals:**
- Avoiding the per-run language-server start in refactor runs (option E in profile.md): excluded by the user.
- A fixed time target: the user chose the scope from the effort/impact curve.
- npm-twin changes.
- Conformance on Python 3.11, 3.12 and 3.14 in CI (approved coverage cut).

## Decisions

1. **Base on DEV-2301, not `main`.** Options: `main`; DEV-2302 only; DEV-2301. DEV-2301 is a large performance change
   in itself, so CI is profiled and cut on top of it. (user)
2. **Profile and optimize in one change**, overriding the issue's "Not in scope: making the changes". (user)
3. **No fixed time target**; the scope was chosen from the effort/impact curve in profile.md. Options: slowest job
   ≤ 5 min; a relative cut; the curve. (user)
4. **Scope: A, B, C, D1, D2; not E** (profile.md, "Options"). (user)
5. **The profile lives in this change folder** (`profile.md`), not in Linear or `docs/`: a dated snapshot tied to
   the commit it measured, archived with the change. (default)
6. **A stays on this branch**, not DEV-2301's. (default)
7. **A: the follow stops at a file whose `SourceFileInfo` is missing, `isThirdPartyImport` or `isTypeshedFile`.**
   The profile shows 18 s of a 22 s test in basedpyright's stub→source mapping reached through the transitive
   follow; with the guard, the 1,552 affected tests (refactor, compliance, keyed, union, index and export tests and
   conformance cases) pass unchanged and their summed time falls from 1,493 s to 761 s. Direct `definition` and
   `typeDefinition` answers are unchanged: only the transitive follow stops. The private export protocol changes
   (fewer `followed` facts); command output does not, so no spec changes. (default; framing (codex))
8. **A is pinned three ways** (codex): no `followed` fact lies in a library or typeshed file for a project whose
   model subclasses `pydantic.BaseModel`; a first-party chain (class → field annotation → class → field annotation)
   is still followed; a direct `definition` that lands in pydantic or typeshed is still returned. The existing
   refactor conformance cases on pydantic projects pin the command output. No separate test for a missing
   `SourceFileInfo`: a defensive branch with no natural fixture.
9. **B: `pytest-split` with committed duration files**, rather than a hand-written hash split: single tests take
   20–60 s, so an unweighted split is badly unbalanced. (default)
10. **B: shard counts `test` ×2, `cross-twin` ×3**: 14 heavy jobs plus `package`, `node`, `acceptance-node-only`
    and `plugin` = 18, within the GitHub Free plan's 20 concurrent jobs (the org's plan; the repo is public, so
    minutes are free). (default)
11. **B: durations come from `pytest-split --store-durations`**, run in a temporary CI step on this branch for each
    job kind and committed; JUnit is not converted. Three files, one per job kind (Python suite, cross-python,
    cross-typescript), because the same node id costs different time per twin. Stale or missing entries only
    affect balance (pytest-split gives unknown tests the average). The refresh is documented in
    `docs/development.md`. (codex)
12. **B: a partition test per job kind** (codex): under each kind's real environment (`LA_CONFORMANCE_CROSS`,
    `LA_CONFORMANCE_TWIN`, the twins' bin dirs, and the `test` jobs' conformance deselection), every collected node
    id lands in exactly one group of that kind's split.
13. **B: ruff, basedpyright and `sync-shared --check` run in shard 1 only** of each Python version, so shards do not
    repeat them. (codex)
14. **C: one module per command** (`living_architecture/cli/<command_snake>.py`, e.g. `cli/la_config.py` with
    `la_config()`), not imports inside functions: imports stay at the top of every file. `cli/__init__.py` keeps only
    the shared helpers (`_run`, `_root`, `_checked_root`, `_argv`) and imports no command package. The moves go
    through `la:deterministic-refactor`. (default)
15. **C is pinned for every lightweight command** (codex, partly): `la-config`, `la-doctor` (including `--twin` and
    `--contract-hash`) and every review shim (`la-fetch-coderabbit-threads`, `la-reply-invalid-coderabbit`,
    `la-reply-to-pr-thread`, `la-fetch-failed-pr-checks`, `la-wait-for-reviews`, `la-pr-reviewers`), run in a
    subprocess, load none of `rope`, `living_architecture.refactor`, `.archcheck`, `.c4`, `.conventions`,
    `.typecheck` or `.affected`. No time budget: flaky on shared runners. (default for the module set; scope
    (codex))
16. **D: the `test` jobs pass `--deselect tests/test_conformance.py::test_case`**; the runner's own tests in that file
    still run, and local `uv run pytest -q` still runs everything. D1 (drop the duplicate on 3.13) is subsumed by D2
    (drop it on every version). (user)
17. **Rejected (codex): keep one conformance shard on each of Python 3.11, 3.12 and 3.14.** The user approved
    running conformance on 3.13 only, knowing it is a coverage cut.

## Risks / Trade-offs

- [A hides a fact a rule needs from a library class] → every refactor and compliance test and conformance case
  passes with the guard; the pydantic conformance cases pin output; decision 8 pins what is still followed.
- [Version-specific behaviour regresses on 3.11/3.12/3.14 unseen by conformance] → accepted by the user; the
  non-conformance suite still runs on every version.
- [Shards drift out of balance as tests change] → balance only; the partition test guarantees coverage; refresh
  documented.
- [Runner speed varies up to ~1.6× between jobs] (profile.md: `test (3.14)`) → before/after compare summed test
  time per job kind as well as wall-clock.
- [DEV-2301 changes `pyright_export.cjs` again before merging] → merge its branch into this one and re-run the local
  scope.

## Migration Plan

CI-only and internal; no migration. Rollback is a revert of the workflow and the module split.
