## Why

Every skill pinned the tools version it was written for (`la-doctor --expect <version>`), so each release
rewrote the same pin in every skill. The plugin already declares its version in `plugin.json`.

## What Changes

- `la-doctor --plugin DIR` checks the installed tools against the `version` of the nearest
  `.claude-plugin/plugin.json` at or above DIR. `--expect` stays for skills of older plugins.
- Three new problem texts: `doctor.plugin-not-found`, `doctor.plugin-invalid`, `doctor.plugin-unreadable`.
- Every skill's preflight becomes `la-doctor --plugin <this skill's base directory>`; the skills test forbids
  `--expect` pins.
- The conformance runner substitutes placeholders in `write` step texts.

## Capabilities

### New Capabilities

### Modified Capabilities
- `shared-contract`: `la-doctor` checks the tools against the calling plugin's version.

## Impact

- `shared/cli.yaml`, `shared/findings.yaml` and the twins' snapshots; `python/src/living_architecture/doctor/`,
  `node/src/doctor/`, both CLIs.
- `plugin/skills/*/SKILL.md`, `python/tests/test_skills.py`, `README.md`, `AGENTS.md`.
- `conformance/cases/doctor-plugin-*`, `conformance/INVENTORY.md`, `conformance/README.md`,
  `python/tests/test_conformance.py`.
