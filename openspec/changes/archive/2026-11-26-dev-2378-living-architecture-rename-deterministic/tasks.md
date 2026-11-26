Calibration notes (read first):
- The substitution is `rename_deltas.py`'s `RULES` (this folder), applied in order, case-sensitive; reuse it for code,
  tests and docs rather than re-deriving it. Lockfiles are regenerated, never substituted (design decision 15).
- Tools: run the branch's own `la-*`/`dr-*` (later `trmv-*`) tools from `python/.venv/bin` plus wrappers for the npm
  bins, not the global ones. Mid-rename the tools may be briefly unusable; verify with `commands.typecheck` directly and
  the tests (design decision 10), without stopping.
- pr-tests edits the tests in their CURRENT locations (`python/dr/tests`, `node/dr/test`, `conformance/dr`, …) to
  expect the new names; group 2 moves them with everything else. Goldens are edited by the substitution, never
  regenerated (design decision 8).
- Each `git mv` commit is paired with the edit commit right after it; the pair ends green (design decision 9).
- Harness and skill edits apply only the wording in design.md decisions 2–5; anything else needs the user's OK on the
  exact diff first.

## 1. Tests (pr-tests)

- [x] 1.1 Apply the substitution to both twins' unit tests (imports `trmv` / `type-rename-move/<module>`, bins and entry points `trmv-*`, `TRMV_*`/`Trmv*` identifiers, test names, the `la-typecheck` alias text, install hints, identity lines, `trmv.yaml`, `trmv.schema.json`, `format.trmv-*`); verify they fail only for the missing names
- [x] 1.2 Apply the substitution to every conformance case (commands, fixtures, goldens, case and fixture names containing `dr`, both `INVENTORY.md` files and `conformance/README.md`); verify the corpus fails only for the missing names
- [x] 1.3 Rename the test and case ids in the six `tests/durations/*.json` files to match 1.1–1.2
- [x] 1.4 Update the skills, docs and plugin tests for the `trmv` plugin, `trmv:rename-move`, `docs/rename-and-move.md` and the marketplace entry
- [x] 1.5 Add release-rule tests: `scripts/release-check` with `trmv--v<version>` at the release commit passes, missing or at another commit exits 1 naming the tag (and both commits); the `v0.13.0` → 0.14.0 formats transition reads `shared/config.yaml` at v0.13.0 and `shared/trmv/config.yaml` at HEAD
- [x] 1.6 Add the guard test to la's suite (design decision 6: patterns, path scan, exclusions incl. specs pending an active change); verify it fails listing today's names
- [x] 1.7 Extend the npm pack test: la's tarball imports only `type-rename-move/<module>`, and every export subpath resolves from the packed tarballs

## 2. Layout and packages (pr-implement)

- [x] 2.1 `git mv` `python/dr` → `python/trmv`, `node/dr` → `node/trmv`, `shared/dr` → `shared/trmv`, `conformance/dr` → `conformance/trmv`, `plugin/dr` → `plugin/trmv`, `plugin/trmv/skills/deterministic-refactor` → `plugin/trmv/skills/rename-move`, `docs/deterministic-refactoring.md` → `docs/rename-and-move.md`, `shared/trmv/schema/deterministic-refactor.schema.json` → `trmv.schema.json`; commit as renames
- [x] 2.2 Follow the moves in workspace members, package names (`type-rename-move`), la's dependency pins, `node/la/tsconfig*.json` paths, `scripts/sync-shared`, `scripts/release-check`, `scripts/release_rule.py` (`FORMATS_FILE`, keeping the `shared/config.yaml` fallback), `node/scripts/conformance.mjs`, the conformance runner's `PACKAGES`; regenerate `uv.lock` and `package-lock.json`; verify `uv sync --locked --all-packages`, `npm ci`, `scripts/sync-shared --check`
- [x] 2.3 Rename the Python package `deterministic_refactor` → `trmv` with `dr-refactor` (fallback: `git mv` + rewrite), commit as renames; then rewrite la's npm specifiers `deterministic-refactor/*` → `type-rename-move/*`; verify `commands.typecheck` and both twins' unit tests

## 3. Contract and twins

- [x] 3.1 Apply the substitution to `shared/trmv/` (`cli.yaml` package/plugin/doctor and command names, findings and ids, `config.yaml` files and series, schema `$id` and descriptions, `languages.yaml` install templates and runners, vectors, README) and `shared/la/` (the `$ref`, the alias finding, README); run `scripts/sync-shared`; verify the drift tests
- [x] 3.2 Rename commands, bins, entry points, identifiers and texts in both twins; replace hard-coded package-level names with reads from the contract (design decision 11); verify both twins' unit tests
- [x] 3.3 Verify both conformance trees through both twins (`scripts/conformance-cross`) and that `LA_UPDATE_GOLDENS=1` produces no golden diff
- [x] 3.4 Implement the plugin-tag check in `scripts/release-check`; verify the 1.5 tests

## 4. Plugins, skills and harnesses

- [x] 4.1 Rename the plugin (`plugin/trmv/.claude-plugin/plugin.json` name `trmv`), la's plugin dependency `{name: trmv, version: "~0.14.0"}`, the marketplace entry; apply the substitution to every skill (`trmv:` names, `trmv-*` commands, `trmv:rename-move` heading and description per design decision 3); verify `plugin validate` on `plugin/trmv` and `plugin/la` and the skills tests
- [x] 4.2 Apply the approved `index.yaml`, `model.c4` and `system.arc42.md` edits (design decision 4) and regenerate diagrams with `la-arch-diagrams`; verify `la-arch-check` and `npx likec4 validate`

## 5. Docs, CI and metadata

- [x] 5.1 Apply the substitution and design decision 3 to `README.md`, `AGENTS.md`, `CONTRIBUTING.md`, `docs/*` (incl. the runbook tagging `trmv--v<version>` from `plugin/trmv`), both package READMEs and docstrings
- [x] 5.2 Update `.github/workflows/ci.yml` (matrix `[trmv, la]`, `plugin validate plugin/trmv`), `publish.yml` (`uv build --package type-rename-move`, `npm -w trmv`, trmv before la) and `scripts/acceptance-node-only`
- [x] 5.3 Add the keywords of design decision 17 to both trmv package manifests
- [x] 5.4 Verify the guard test passes

## 6. Finish

- [x] 6.1 Run the enforcement bundle (`la-arch-check`, `npx likec4 validate`, `trmv-typecheck` against its baseline), the release-rule tests and the local test scope
- [x] 6.2 Put in the PR description the maintainer re-setup: link `~/.claude/skills/trmv` → `plugin/trmv`, re-link `~/.claude/skills/la` → `plugin/la`, reinstall with `uv tool install -e python/la --with-editable python/trmv --with-executables-from type-rename-move`
- [x] 6.3 Edit the DEV-2371 comment in place to design decision 5's wording
- [x] 6.4 At archive time (pr-review): after `openspec archive`, apply `rename_deltas.py`'s substitution to the scenario titles and the Purposes of `refactor`, `typecheck` and `doctor` in `openspec/specs/`; verify `openspec validate --strict --all` and the guard test
