## Why

`la-doctor --plugin` requires the installed tools' version to equal `plugin.json`'s, and the versions move together
at every release, so every release forces a tools reinstall, even 0.4.1, which changed only skills and docs. The
version stands in for "the tools this plugin was released with" and changes even when the tools do not.

## What Changes

- A **tools fingerprint** (sha256 over the git objects of `shared/`, `conformance/`, `python/src/`, `node/src/` at
  HEAD) is stamped at release into `plugin/.claude-plugin/TOOLS_FINGERPRINT` and into each twin
  (`python/src/living_architecture/TOOLS_FINGERPRINT`, `node/src/TOOLS_FINGERPRINT`, shipped in both packages).
- `la-doctor --plugin` compares the plugin's fingerprint with the twin's bundled one instead of the versions: equal
  is healthy whatever the versions; a different or missing fingerprint reports the new `doctor.tools-mismatch`,
  naming both versions and the invoking twin's own reinstall command; a malformed one reports
  `doctor.plugin-fingerprint-invalid`. `doctor.version-mismatch` goes.
- **BREAKING**: `la-doctor --expect` is removed (no caller; it encoded the dropped version-equality rule).
- New `scripts/release-bump <version>` does the whole release bump: every version (with lockfiles), the doc pins
  and the fingerprint, all or nothing. `scripts/release-check` also verifies the fingerprint, so `Publish` refuses a
  stale one.
- `node/package.json`'s `prepack` builds `dist/` first, so `npm pack` never ships a stale or missing `dist/`.
- Conformance: a `<TOOLS_FINGERPRINT>` placeholder; new, updated and removed `la-doctor` cases.
- Docs: `AGENTS.md`, `docs/development.md` "Releasing", `docs/commands.md`, README Install.

## Capabilities

### New Capabilities

### Modified Capabilities

- `shared-contract`: "la-doctor checks the tools against the calling plugin" is replaced by "la-doctor checks the
  tools fingerprint against the calling plugin" (fingerprints, no `--expect`); a new requirement for the release
  fingerprint (stamping, verification, packaging).

## Impact

- Code: `python/src/living_architecture/{__init__.py,doctor/__init__.py}`, `node/src/{index.ts,doctor/index.ts}`,
  `node/scripts/build.mjs`, `node/package.json`, both CLI layers (via the manifest).
- Contract: `shared/cli.yaml`, `shared/findings.yaml`, `shared/vectors/cli.yaml` (re-synced snapshots).
- Scripts: new `scripts/release-bump` and a shared fingerprint module under `scripts/`; `scripts/release-check`.
- Tests: conformance runner and cases, `test_versions.py`, `test_packaging.py`, `test_skills.py`,
  `test_doctor.py`, release-script tests; `node/test/{package,packaging,doctor}.test.ts`.
- Users: a plugin update that leaves the tools unchanged needs no reinstall. A plugin released before this change
  (no fingerprint) reports a mismatch with the newer tools, whose reinstall command names that plugin's version.
