## Why

The package split out in DEV-2320 type-checks, renames and moves; it does not do every refactor, so
"deterministic-refactor" overpromises. It has never reached PyPI or npm (the 0.14.0 release was undone), so this is
the last moment to rename it without a migration. npm refuses `trmv` as a package name ("too similar to existing
packages"), so the distribution is `type-rename-move` and everything agents type is `trmv`.

## What Changes

- **BREAKING** (unreleased names) The PyPI and npm package `deterministic-refactor` becomes `type-rename-move`; its
  Python import package `deterministic_refactor` becomes `trmv`, and la's npm imports `deterministic-refactor/<module>`
  become `type-rename-move/<module>`.
- **BREAKING** (unreleased names) The commands `dr-refactor`, `dr-typecheck`, `dr-compliance`, `dr-mock-lint`,
  `dr-doctor` and `dr-config` become `trmv-*`, with no aliases. `la-typecheck` stays the deprecated alias, now of
  `trmv-typecheck`.
- **BREAKING** (unreleased names) The plugin `dr` becomes `trmv` (tag `trmv--v<version>`, la's plugin dependency and the
  marketplace entry follow); its skills move to the `trmv:` namespace, and `deterministic-refactor` becomes
  `trmv:rename-move`.
- **BREAKING** (unreleased names) The config file `deterministic-refactor.yaml` becomes `trmv.yaml` (format series
  `[0.14.0]`); its schema becomes `trmv.schema.json`.
- Every finding, hint, identity line and install command naming dr or `deterministic-refactor` names trmv or
  `type-rename-move` (finding ids `format.dr-*` become `format.trmv-*`).
- `scripts/release-check` also refuses a release whose `trmv--v<version>` plugin tag is missing or not at the release
  commit.
- The repo layout (`python/`, `node/`, `shared/`, `conformance/`, `plugin/` subdirectories), identifiers, scripts, CI,
  the architecture model and arc42, docs (`docs/deterministic-refactoring.md` becomes `docs/rename-and-move.md`; the
  concept is "verified renames and moves") and both packages' keywords follow.
- A permanent test keeps the retired names out of the repo outside archived OpenSpec changes.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `refactor`: the commands are `trmv-refactor`, `trmv-compliance` and `trmv-mock-lint`; routing, hints and paths name
  trmv.
- `typecheck`: the command is `trmv-typecheck`; `la-typecheck` is its deprecated alias.
- `doctor`: `trmv-doctor` checks the trmv tools and the config trmv reads; `la-doctor` checks the trmv installation.
- `repo-config`: the config file `trmv.yaml` and its format series; `trmv-config`.
- `shared-contract`: the contract in `shared/trmv/`, the trmv manifest names, findings and release rules over the
  renamed layout; `release-check` verifies the trmv plugin tag.
- `twin-forwarding`: the twin runners and install hints name `type-rename-move` and `trmv-*`.
- `arch-check`: the `source_roots` example and dr references in its requirements name trmv.

## Impact

- Code: every module of the trmv twins moves (`python/trmv/src/trmv`, `node/trmv/src`); la's imports of it, its install
  hints and its twin lookup follow.
- Distribution: a new package name on both registries (trusted publishers set up outside this change); the plugin
  `trmv` in the marketplace; the release runbook tags `trmv--v<version>` from `plugin/trmv`.
- Target repos: none; nothing named dr was ever released. Users of the maintainer's local setup re-link
  `~/.claude/skills/trmv` and reinstall the editable tools (PR description).
- Repo: `shared/`, `conformance/`, `plugin/`, `architecture/`, `openspec/specs/`, CI, publish, `scripts/`, docs, both
  lockfiles and the test duration files.
