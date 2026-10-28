## Why

`la-doctor --plugin` requires the installed tools' version to equal `plugin.json`'s, and the versions move together
at every release, so every release forces a tools reinstall, even 0.4.1, which changed only skills and docs. A
machine-checked release convention removes that: a release that changes the tools raises the minor (or major)
version, one that does not may raise only the patch, so every release in a minor series ships the same tools and
`la-doctor` need compare only major.minor.

## What Changes

- `la-doctor --plugin` is healthy when the plugin's and the installed tools' major.minor agree, whatever follows.
  A plugin `version` must be `<digits>.<digits>.<anything>` (so `0.4.1-rc1` is valid); otherwise
  `doctor.plugin-invalid`, reworded. A different series reports `doctor.version-mismatch`, reworded to name the
  series and the invoking twin's own reinstall command.
- **BREAKING**: `la-doctor --expect` is removed (no caller; it encoded exact version equality).
- A release rule, defined once under `scripts/`: when the tool inputs (`shared/`, `conformance/`, `python/src/`,
  `node/src/`, `node/scripts/`, `node/tsconfig*.json`, and the package manifests and lockfiles beyond their own
  version) changed since the previous release tag, the new version must raise major or minor.
  `scripts/release-check` enforces it at publish time (and verifies HEAD is the tag); a test enforces it on the
  version-bump PR, before any tag exists. `ci.yml` and `publish.yml` check out full history.
- `node/package.json`'s `prepack` builds `dist/` first, so `npm pack` never ships a stale or missing `dist/`.
- Conformance: `<MAJOR>`/`<MINOR>` placeholders; new, reworded and removed `la-doctor` cases.
- Docs: `AGENTS.md`, `docs/development.md` "Releasing", `docs/commands.md`, README Install.

## Capabilities

### New Capabilities

### Modified Capabilities

- `shared-contract`: "la-doctor checks the tools against the calling plugin" is replaced by "la-doctor checks the
  tools' minor series against the calling plugin" (series comparison, no `--expect`); a new requirement that a
  release changing the tools raises the minor version.

## Impact

- Code: `python/src/living_architecture/doctor/__init__.py`, `node/src/doctor/index.ts`, both CLI layers (via the
  manifest), `node/package.json`.
- Contract: `shared/cli.yaml`, `shared/findings.yaml`, `shared/vectors/cli.yaml` (re-synced snapshots).
- Scripts and CI: a release-rule module under `scripts/`, `scripts/release-check`, `.github/workflows/{ci,publish}.yml`.
- Tests: conformance runner and cases, `test_cli_parser.py`/`parser.test.ts` (vectors), `test_doctor.py`,
  `doctor.test.ts`, `test_versions.py`, new `test_release_scripts.py`, `test_skills.py`,
  `node/test/{package,packaging}.test.ts`.
- Users: a plugin update within the same minor version needs no reinstall. Older tools (exact-equality doctor)
  still report a mismatch against any other plugin version.
