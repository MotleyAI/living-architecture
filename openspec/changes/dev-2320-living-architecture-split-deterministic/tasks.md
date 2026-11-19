Calibration notes (read first):
- Every step below ends green (its tests plus `la-arch-check`) and is committed on its own; moves are committed as
  renames, separately from edits, so git and reviewers see them as renames.
- The test stage writes failing tests for groups 1, 2 and 5–8 against the current layout where the code still lives
  (cases under today's `conformance/cases/` with `golden: manual`, unit tests under today's `python/tests` and
  `node/test`); group 3 moves them with everything else. Cases that only make sense in the split layout (package-aware
  runner, dr-only repos, two doctors) are written as `golden: manual` cases whose expected output is the spec's, and
  are expected to fail until groups 3–6 land.
- Group 3's moves leave `la-arch-check` red until the model split: task 8.1 runs directly after 3.6, with its
  approved wording, and the commits inside group 3 are green on their tests but not on `la-arch-check`.
- Golden updates (`LA_UPDATE_GOLDENS=1`) carry a reason per golden in the commit message; never absorb an
  unexplained diff.
- Harness edits (architecture/, skills) apply only the wording approved in design.md; any other wording needs the
  user's OK first, shown as an exact diff. Skill edits beyond mechanical renames (`la-typecheck` → `dr-typecheck`,
  `la:<moved skill>` → `dr:<moved skill>`, `la-doctor` → `dr-doctor` and `la-config` → `dr-config` in dr skills)
  need the user's OK on the exact wording before they land.

## 1. Python source_roots in index.yaml

- [x] 1.1 Add `source_roots` to the `python` section of `shared/schema/index.schema.json` (exclusive with `source_root`), its findings to `shared/findings.yaml` (both forms set, malformed, invalid or overlapping entry, root package in no entry, in several entries, unused entry), run `scripts/sync-shared`; verify the drift test passes
- [x] 1.2 Implement `source_roots` in both twins' index loaders and Python unit discovery (each root package resolved under exactly one entry, dotted ids), and reject it in the `typescript` section; verify the new arch-check conformance cases (one per scenario of "Python roots may sit under several source roots" and the modified arch-check requirements) pass through both twins
- [x] 1.3 List the new cases in `conformance/INVENTORY.md`; verify the inventory test passes

## 2. Top-level exempt, format 0.13.0 and the version bump

- [x] 2.1 Move `exempt` to the top level of the config schema (dr-owned definition, still one schema file at this step), retire `conventions.exempt`, append `0.13.0` to the released formats, and bump `python/pyproject.toml`, `node/package.json` (and lockfiles) and `plugin/.claude-plugin/plugin.json` to 0.13.0 in the same commit; verify `test_versions` and the release-rule tests pass
- [x] 2.2 Make language detection and the conventions gate read the top-level `exempt` in both twins (keeping tracked-or-untracked-not-ignored file listing); verify the repo-languages and conventions cases, incl. "Exempt files do not make a language" and "Exempt paths come from the top-level key"
- [x] 2.3 Implement the 0.4.0 → 0.13.0 step of `la-arch-migrate` in both twins (textual move after `format`, dedent, empty `conventions` removed, not-migratable shapes); verify one case per scenario of "la-arch-migrate moves the exempt key", byte-identical across twins
- [x] 2.4 Migrate this repo's `living-architecture.yaml` (`exempt: ['conformance/*']`, `format: 0.13.0`) with the new `la-arch-migrate`; re-bless goldens whose only change is the format value or the `exempt` key, with reasons; verify the full local scope passes

## 3. Workspaces and module moves

- [x] 3.1 Turn `python/` into a uv workspace root (members `dr`, `la`, `conformance`), create `python/dr/pyproject.toml` (`deterministic-refactor`, 0.13.0, rope/basedpyright/pydantic/pyyaml/jsonschema deps as needed) and `python/la/pyproject.toml` (`living-architecture`, depends on `deterministic-refactor>=0.13.0,<0.14` from the workspace); verify `uv sync --locked` in `python/`
- [x] 3.2 Move `contract`, `config`, `lang`, `twin`, `changes`, `typecheck`, `refactor` and the dr CLI entry points to `python/dr/src/deterministic_refactor/` with `dr-refactor` (dogfooding); if it cannot move across source roots or packages, STOP and ask the user before any fallback; verify `dr-typecheck`/basedpyright, `dr-mock-lint` and the moved tests pass
- [x] 3.3 Split `config` so dr holds loading, YAML profile, schema, defaults, format check/stamp and language detection, and la holds only la's resolved-config model; parametrise `twin` by package identity (doctor command, runner, install, hashes); split `cli` per package; give each package its own `__version__`/`NATIVE_LANGUAGE`; verify la imports only the public dr modules listed in design decision 22
- [x] 3.4 Move `python/tests` into `python/dr/tests` and `python/la/tests` by the module they test; move the conformance runner into the dev-only `python/conformance` member; verify both packages' suites collect and pass
- [x] 3.5 Turn `node/` into a private npm workspace root with `node/dr` (`deterministic-refactor`) and `node/la` (`living-architecture`, `"deterministic-refactor": "~0.13.0"`), moving modules as in 3.2–3.3 with `dr-refactor` (same stop rule); `node/la/tsconfig.json` maps `deterministic-refactor` to `../dr/src`, `node/la/tsconfig.build.json` resolves dr's built declarations; dr builds first; verify `npm ci`, lint, typecheck, `npm test` in both workspaces and a pack test proving la's tarball imports only `deterministic-refactor`
- [x] 3.6 Update `living-architecture.yaml` `commands.test`/`lint`/`typecheck` to cover both workspaces in both ecosystems; verify each command runs green

## 4. Contract split

- [x] 4.1 Split `shared/` into `shared/dr/` and `shared/la/` as design.md lists (schemas with property-level `$ref` from la's to dr's, findings, cli manifests, languages registry with `{package}` runner/install templates, config file names and per-file format series in `shared/dr/config.yaml`, vectors, README per directory); verify the old `shared/` top level holds only the two directories
- [x] 4.2 Update `scripts/sync-shared` for four snapshots (each package's own directory, own `CONTRACT_HASH`); verify `scripts/sync-shared --check` and the drift tests of all four snapshots
- [x] 4.3 Teach both twins' default fillers to follow `$ref`; la registers dr's schema from dr's snapshot; la's message lookup falls back to dr's registry; add the id-uniqueness test; verify the schema/default vectors (empty config, partial `commands`, explicit null, unknown dr key, unknown la key) in both twins

## 5. Commands

- [x] 5.1 Rename `la-typecheck` to `dr-typecheck` (dr manifest, entry points, bins) and add the `la-typecheck` alias to la with its deprecation finding (not printed under `LA_FORWARDED`, not on `--help`); verify the alias scenarios through both twins
- [x] 5.2 Implement config-file resolution (dr file else la file; la commands read only the la file), the both-files refusal before the format check, dr's key set for `deterministic-refactor.yaml`, and the per-file format check with dr's refusal texts, in both twins; verify every scenario of "Each package reads one committed config file" and the modified format requirement
- [x] 5.3 Implement `dr-config get|show` in both twins; verify its scenarios and that `la-config get` still accepts every key
- [x] 5.4 Implement `dr-doctor` (plugin, both-files, format, require-config naming `/dr:init`, schema, git and language executables, ok line, `--contract-hash`, `--twin`) and extend `la-doctor` (both-files, dr-installation check with la's install command, two-hash `--twin`, package-named version mismatch); verify every scenario of the doctor spec and the modified identity requirement
- [x] 5.5 Make each public entry point run exactly one format check in the invoking twin before forwarding, and pass the resolved config to dr library calls from la; verify "Format refused before forwarding" and the forwarded-environment recursion refusal for dr and la commands

## 6. Conformance split

- [x] 6.1 Split `conformance/cases` into `conformance/dr/cases` and `conformance/la/cases` by the command each case invokes (`la-typecheck` cases become `dr-typecheck` cases), each tree with its `INVENTORY.md`; keep `conformance/fixtures/` shared; update `conformance/README.md`; verify both inventory tests
- [x] 6.2 Make the runner package-aware (tree decides manifest, format series, version, hash placeholder, Python entry points, npm bins; both packages' commands on `PATH`; host runners hidden) with the self-test refusing cross-package invocations; update `node/scripts/conformance.mjs` and `scripts/conformance-cross`; verify both trees through both twins
- [x] 6.3 Add the remaining required cases: the alias and its stderr line; the format matrix for both file names; both-files refusal from a dr and an la command; local file ignored by dr; both doctor identities and hashes; a wrong dr version or hash on `PATH` for `la-doctor`; the uvx/npx fallback command lines naming each package; dr missing after a plain la install; finding-template coverage per corpus; verify each passes through both twins and every template of both registries is produced
- [x] 6.4 Re-bless goldens changed only by an explained cause (install hints naming the package, the ok line's package, runner and identity lines, paths), listing each reason in the commit message; verify `scripts/conformance-cross` over both trees

## 7. Plugins and skills

- [x] 7.1 Split `plugin/` into `plugin/dr/` (`.claude-plugin/plugin.json` `dr` 0.13.0; skills deterministic-refactor, make-refactor-target-compliant, make-diff-compliant; `languages/`) and `plugin/la/` (`plugin.json` `la` 0.13.0 with `dependencies: [{name: dr, version: "~0.13.0"}]`; every other skill); list both in `.claude-plugin/marketplace.json`; verify `npx -y @anthropic-ai/claude-code plugin validate plugin/dr` and `plugin/la`
- [x] 7.2 Apply the mechanical skill renames (dr skills: `dr-doctor --plugin`, `dr-config`, `dr-typecheck`; la skills: `dr:` skill names, `dr-typecheck`); verify the skills tests (manifest references, language-neutral, dr skills name only dr commands)
- [x] 7.3 Draft `dr:init` and the `la:init` hand-off (dr keys and baseline step to `dr:init`), show the user the exact wording, apply only after the OK; verify the skills tests
- [ ] 7.4 At release time, after the maintainer's re-setup (9.5), apply the approved edit to the user's global `~/.claude/CLAUDE.md` (`la:deterministic-refactor` → `dr:deterministic-refactor`, `la-typecheck` → `dr-typecheck`)

## 8. Architecture harnesses

- [x] 8.0 Implement root-package nodes claiming their root's top-level units in both twins' claims checks; add one conformance case per new arch-check scenario (Python through both twins, TypeScript), list them in `conformance/INVENTORY.md`; verify they pass through both twins
- [x] 8.1 Apply the approved `index.yaml`, `model.c4`, `views.c4` and `system.arc42.md` edits (design decision 12), add `cross_cutting_specs.doctor` touching `python.dr.doctor` and `python.la.doctor`, move spec mappings and `touches:` to nested ids, regenerate diagrams with `la-arch-diagrams`; verify `la-arch-check` exits 0 and `npx likec4 validate` passes

## 9. CI, publishing, scripts and docs

- [ ] 9.1 Update `.github/workflows/ci.yml`: per-package pytest/ruff/basedpyright, packaging job building and installing all four artifacts (an la-only install resolving dr; a `uv tool install` proving which executables reach `PATH`), node job over both workspaces, cross-twin over both trees, node-only acceptance packing both, `plugin validate` on both plugins; verify the workflow runs green on the PR
- [x] 9.2 Update `.github/workflows/publish.yml` (build with `uv build --package`, `npm -w` build/publish, dr before la) and `scripts/release-check` plus `scripts/release_rule.py` (lockstep across four package versions, two `plugin.json`, la's pin and plugin dependency; per-package hashes; per-file format series read against the pre-split layout); verify the release-rule tests incl. the new scenarios
- [ ] 9.3 Update `scripts/acceptance-node-only` (packs and installs both npm packages); verify the acceptance job
- [x] 9.4 Update `AGENTS.md`, `README.md`, `CONTRIBUTING.md` and `docs/*` for the two packages, commands, plugins, config files and migration; add dr's package README; verify the docs build/links tests and that no doc names `la-typecheck` except as the deprecated alias
- [x] 9.5 Put in the PR description the maintainer's local re-setup: re-link `~/.claude/skills/la` → `plugin/la` and `~/.claude/skills/dr` → `plugin/dr`; reinstall editable tools with `uv tool install -e python/la --with-editable python/dr --with-executables-from deterministic-refactor`

## 10. Finish

- [ ] 10.1 At archive time, rewrite the `## Purpose` of `openspec/specs/typecheck/spec.md` to name `dr-typecheck` (a delta cannot change a Purpose); verify `openspec validate --strict --all`
- [x] 10.2 Run the enforcement bundle (`la-arch-check`, `npx likec4 validate`, `dr-typecheck` against its baseline) and the full local test scope; verify all green
