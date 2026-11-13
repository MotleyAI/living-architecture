## Why

The first round declared `format` and made `la-arch-migrate` convert an unversioned repo, but a repo that declares an
older released format is refused by every command and by `la-arch-migrate` itself (`arch-migrate.unknown-format`).
The first release that changes the format would leave every `0.4.0` repo stuck: migration has no per-format step,
and nothing ties a format-changing release to a conversion.

## What Changes

- `shared/config.yaml`: `format: 0.4.0` becomes `formats: [0.4.0]`, every released format oldest first; the current
  format is its last entry. Both twins and the conformance runner read it there.
- `la-arch-migrate` in both twins becomes a chain of steps keyed by source format (no format → `0.4.0`: today's
  layout and arc42 conversions; then each released format → the next). It runs every step from the declared format
  to the current one in one transaction, verified and all-or-nothing, with one rollback across the whole chain, and
  prints the net effect: each changed path once, by its final state.
- Stamping replaces an existing `format` value as well as inserting a missing one; new `stamp` vectors.
- A declared older format that no release used stays refused, reworded; the stamp refusal says to set the format by
  hand; the `la-arch-migrate` help describes the chain.
- Enforcement: each twin tests that every released older format has a step targeting the next released format;
  the release rule (applied by `scripts/release-check` and the bump-PR test) requires a release that changes
  `formats` to append exactly its own version.
- The `la:pr` preflight migrates a missing or an older format without asking; the docs name the per-format steps.

## Capabilities

### New Capabilities

### Modified Capabilities
- `c4-layout`: `la-arch-migrate` converts a declared released older format step by step, replaces an existing
  `format` value when stamping, rolls back the whole chain, and reports the net effect.
- `repo-config`: the current format is the last of the shared contract's released formats.
- `shared-contract`: a release that changes the released formats appends exactly its own version.

## Impact

- `shared/config.yaml`, `shared/vectors/format.yaml`, `shared/findings.yaml`, `shared/cli.yaml`; both snapshots via
  `scripts/sync-shared`.
- Python: `contract/snapshot.py`, `config/format.py`, `c4/migrate.py`; npm: `contract/snapshot.ts`,
  `config/format.ts`, `c4/migrate.ts`; the conformance runner (`python/tests/test_conformance.py`).
- `scripts/release_rule.py` (and through it `scripts/release-check` and `python/tests/test_versions.py`).
- Goldens re-blessed for the reworded texts (`arch-migrate-format-unknown-older`, any help golden).
- `plugin/skills/pr/SKILL.md`, `docs/development.md`, `docs/configuration.md`, `docs/how-it-works.md`,
  `docs/commands.md`.
- No model, views or arc42 change.
