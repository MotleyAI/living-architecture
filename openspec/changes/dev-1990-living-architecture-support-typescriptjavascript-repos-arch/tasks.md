## 1. Freeze the goldens (pr-tests stage, BEFORE any code moves)

- [x] 1.1 Inventory every output and exit branch of every current command (`la-*`, `dr-*`, including argparse usage errors, unreadable/syntax-error files, missing paths, malformed `.c4`/views, multiple simultaneous findings and their order, every finding template and each value type it is rendered with). Record it as `conformance/INVENTORY.md`, mapping each branch to the case id that covers it. Verify that every branch maps to a case.
- [x] 1.2 Write the conformance runner (`tests/test_conformance.py`, pytest, parametrized over `conformance/cases/*/case.yaml`). It materializes a case into a temp dir: fixture, overlay, and deterministic git history (commits, branches, local bare `origin`, staged/unstaged/untracked/deleted/renamed). It runs the installed command as a subprocess with `LC_ALL=C`, `TZ=UTC`, `COLUMNS=80`, fixed `GIT_*` identity and dates, and no network. It normalizes only the temp root to `<ROOT>` and byte-compares exit, stdout and stderr. `LA_UPDATE_GOLDENS=1` writes the goldens. Verify that a deliberately wrong golden fails with a diff and stays untouched.
- [x] 1.3 Author `conformance/cases/` covering the whole inventory, each case declaring `kind` (neutral/paired/adapter). For `la-check-conventions`, cover each rule, waivers and both text-ratio groups via `--file`, plus git-diff cases (committed, staged, unstaged, deleted, renamed, untracked). Add accepted and rejected invocation vectors for every command, including `--bas` (abbreviation: currently accepted; the post-change golden is exit 2) and the lax config scalars (`'true'`, `1`, `'0.2'`: post-change exit 1 naming the key), each recorded as a deliberate change in a case note. Verify that `LA_UPDATE_GOLDENS=1 pytest tests/test_conformance.py` generates every golden from the CURRENT tool.
- [x] 1.4 Run the runner across Python 3.11, 3.12 and 3.13 (`uv run --python 3.1x`). Add declared normalizations or dedicated cases for any version-dependent text. Verify that the goldens pass unchanged on all three.
- [x] 1.5 Commit the corpus plus goldens as the frozen baseline. Verify that the full suite is green on the unchanged code.

## 2. New-behaviour tests (pr-tests stage, failing until implemented)

- [x] 2.1 Contract vectors under `shared/vectors/`:
  - canonical repr (quotes, escapes, non-printables, nested list and mapping, bool, None, float)
  - glob dialect (separators, `**`, root-level names, dot dirs, case variants, near misses, including the Python test-file parity set from the spec)
  - default materialization (absent parents, explicit `false`/`0`/`[]`/`""`, empty or missing file)
  - YAML profile (YAML 1.1 booleans, duplicate keys)
  - regex subset (accept/reject)

  Write Python tests that consume the vectors. Verify they fail with no implementation present.
- [x] 2.2 Contract tests: every findings-registry id is produced by at least one golden; console scripts equal the manifest command set; skill command references are a subset of the manifest; the snapshot equals `shared/` byte-for-byte with modes; `la-doctor` reports the contract hash. Verify they fail now.
- [x] 2.3 `source_root` tests per the `arch-check` spec: absent is unchanged; src layout is resolved with prefix-free module ids; architecture/docs/specs still read from the repo root; absolute, `..`, symlink-escape, non-directory and missing-`root_package` each exit 2 naming `source_root`. Verify they fail now.
- [x] 2.4 Codex review of the tests against the plan (pr-tests Step 2). Verify that the findings are resolved with the user.

## 3. Symmetric layout

- [x] 3.1 `git mv` `pyproject.toml`, `uv.lock`, `src/` and `tests/` into `python/`. Point `readme` and license at the vendored copies. Update `.github/workflows/ci.yml` and `publish.yml` to run in `python/`. Verify that `cd python && uv sync --locked && uv run pytest -q` is green against the frozen goldens.
- [x] 3.2 Create `shared/` (move the review scripts to `shared/scripts/`) and `scripts/sync-shared` (byte-exact copy with modes into `python/src/living_architecture/contract/data/`, writes `CONTRACT_HASH`, vendors `README.md` and `LICENSE` into `python/`). Verify that the snapshot drift test passes after syncing and fails after touching `shared/`.
- [x] 3.3 Update `test_versions` and `test_skills` to the new locations, with the skills command set read from the manifest. Verify that both pass.

## 4. Shared contract data

- [x] 4.1 Write `shared/schema/living-architecture.schema.json` reproducing today's `LaConfig`: strict keys, bounds, the Sonar `if/then`, and defaults. Verify that the resolved-config goldens (`la-config show`) and the default-materialization vectors pass.
- [x] 4.2 Write `shared/schema/index.schema.json`: the shape of today's `index.yaml` plus `source_root`. It must not reject anything that is a finding today. Verify that the arch-check goldens are unchanged.
- [x] 4.3 Write `shared/findings.yaml` holding every finding, verdict and hint text, with `{name}`/`{name!r}` placeholders. Verify that the registry-coverage test passes.
- [x] 4.4 Write `shared/cli.yaml` describing every command's surface (`passthrough` for `la-count-comments` and the review shims, exit codes, help). Verify that the entry-point and invocation-vector tests pass.
- [x] 4.5 Write `shared/conventions.yaml` and `shared/languages.yaml` (Python: extensions, test globs reproducing `is_test_file`, suppression, waiver prefix) and the regex-subset definition. Verify that the glob and regex vectors pass.

## 5. Python restructure into nodes

- [x] 5.1 Create `contract` (snapshot loading via module-relative paths, renderer with canonical repr, glob matcher, default materializer, YAML profile loader, regex-subset check). Verify that every vector test from 2.1 passes.
- [x] 5.2 Move `config.py` → `config` (schema-validated, materialized, then pydantic models with no defaults). Verify that the `la-config` goldens and the config unit tests pass.
- [x] 5.3 Move `arch_diagrams.py` → `c4`, and `arch_check.py` → `archcheck` (language-neutral) + `lang` (Python `ast` units, import targets, rule detectors, comment line sets; returns data only). Thread `repo_root`/`source_root` separately (design D9). Verify that the arch-check and arch-diagrams goldens plus the 2.3 tests pass.
- [x] 5.4 Move `conventions.py` + `comment_count.py` → `conventions` (detectors from `lang`, texts from the registry, test globs from `languages.yaml`). Verify that the conventions and count-comments goldens pass.
- [x] 5.5 Move `shims.py` → `review` (scripts from the contract snapshot) and `doctor.py` → `doctor` (also reports the contract hash). Verify that the review-script tests, shim goldens and doctor goldens pass.
- [x] 5.6 Move the `deterministic_refactor` package → `living_architecture.refactor` (no compatibility shim). Verify that the `dr-*` goldens and the existing refactor/compliance/mock-lint tests pass.
- [x] 5.7 Create `cli`: every command's parser is built from the manifest (`allow_abbrev=False`, `--` honoured, usage → exit 2, passthrough raw argv), and the pyproject scripts point to it. Verify that the full conformance corpus (including the `--bas` → 2 vector) passes.
- [x] 5.8 Add `jsonschema` to the dependencies and refresh `uv.lock`. Verify `uv sync --locked`.
- [x] 5.9 Make `dr-refactor` output deterministic: print rope's changes sorted by path (the
  change descriptions and the changed-file list). Verify that the refactor goldens pass under
  several `PYTHONHASHSEED` values.

## 6. Packaging verification

- [x] 6.1 Add a CI job that builds the wheel and sdist in `python/`, installs each into a clean venv outside the checkout, runs `la-doctor` (checking the contract hash), `la-config show`, and a review shim against the fake `gh`. Verify that the job is green locally via the same script.

## 7. This repo's architecture and agent docs (every `architecture/` edit needs the user's per-edit OK)

- [x] 7.1 Present the exact `architecture/model/la.c4`, `architecture/views.c4` and `architecture/index.yaml` (draft in design D8; `source_root: python/src`, `legacy_arrows: {baseline: 0}`, diagrams mapping) for approval, then write them. Verify that `la-arch-check` exits 0 on this repo and that `npx likec4 validate architecture` succeeds.
- [x] 7.2 Present the exact `architecture/system.arc42.md` (Purpose, Building blocks → view, the principles from design D8 each with a status tag, Rationale) for approval, then write it and run `la-arch-diagrams`. Verify that `la-arch-check` stays at exit 0, including enforced-tags and diagrams-fresh.
- [x] 7.3 Write `AGENTS.md`:
  - the twin rule
  - how to change a parameter, finding, flag or rule (edit `shared/`, run `scripts/sync-shared`, update every twin, add or adjust a conformance case)
  - the case kinds
  - golden regeneration only via `LA_UPDATE_GOLDENS=1` with a stated reason, reviewed in the diff, never to absorb an unexplained difference
  - version and contract-hash lockstep across pyproject, npm (from PR 2) and `plugin.json`
  - the per-side dev and test commands

  Write `CLAUDE.md` containing `@AGENTS.md`. Verify that both files exist and that `CLAUDE.md` imports `AGENTS.md`.
- [x] 7.4 Update `README.md` (layout, editable install `uv tool install -e <checkout>/python`, CI snippet unchanged, Releasing steps now syncing the snapshot). Verify with `scripts/sync-shared` + the drift test.

## 8. Final gates

- [x] 8.1 In `python/`: full non-integration suite, `ruff check src tests`, `basedpyright src tests`. At the root: `npx -y @anthropic-ai/claude-code plugin validate .` and `… plugin validate plugin`. Verify all green.
- [x] 8.2 `la-check-conventions --base main` is clear; `openspec validate dev-1990-living-architecture-support-typescriptjavascript-repos-arch --strict` passes.
- [ ] 8.3 (pr-review, at archive time) Add the spec mapping to `architecture/index.yaml` after the spec directories exist: `arch-check` → node `archcheck` `specs:`; `shared-contract` → `cross_cutting_specs` touching every node (exact edit presented for approval). Verify that `la-arch-check` exits 0 after `openspec archive`.
- [x] 8.4 (pr-review) Validate `root_package` like `source_root` (absolute, empty/`.`/`..` segments, symlink escape out of `source_root`, not a directory → exit 2 naming `root_package`); every layout setup-error text comes from `shared/findings.yaml`, and the invalid-`source_root` cases pin exact goldens. Verify with new conformance cases and the full suite.
