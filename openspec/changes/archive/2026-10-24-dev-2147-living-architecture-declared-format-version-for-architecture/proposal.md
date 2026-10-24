## Why

A repo declares no format version, so every format change is recognised by heuristics: an older `la` on a newer repo
fails with an unrelated setup error (e.g. "nested elements may not carry metadata"), and a newer `la` on an older repo
keeps per-change detection in every reader. The next format change (DEV-2139) would add another such heuristic.

## What Changes

- **BREAKING**: `living-architecture.yaml` declares the repo format in a `format` key: the `la` version that introduced
  the format (`format: 0.4.0`). It versions the whole repo format, the config and everything under `architecture/`.
  The current format comes from `shared/config.yaml`.
- **BREAKING**: every command except `la-arch-migrate`, `la-doctor` and the review shims checks the declared format
  before doing anything else, and exits 2 on any other format: a newer one names the `la` to upgrade to, an older or
  missing one says to run `la-arch-migrate`. The exemption is declared in `shared/cli.yaml`. A repo without a committed
  `living-architecture.yaml` is not checked.
- `la-doctor` reports a format refusal as its problem line.
- `la-arch-migrate` converts the repo to the current format and stamps `format`: for a repo that predates the key it
  applies today's detected step (the legacy `architecture/model/*.c4` layout), then inserts the key textually,
  verified and all-or-nothing together with the layout files. It refuses a newer, invalid or unknown older format
  and a repo without `living-architecture.yaml`. A failed rollback is reported naming the paths it left.
- `la-arch-check` and `la-arch-diagrams` no longer suggest `la-arch-migrate` for a legacy-shaped layout: the format
  check already routes an older repo there, so their layout message always names the files to merge by hand.
- `la:init` writes the config and then runs `la-arch-migrate` to stamp `format`; docs and skills name the field.
- Version 0.4.0 in both twins and the plugin; this repo is stamped `format: 0.4.0`.

## Capabilities

### New Capabilities

### Modified Capabilities
- `repo-config`: the `format` key; the format check every non-exempt command runs; `la-doctor` reports it.
- `c4-layout`: `la-arch-migrate` converts to the current format and stamps it; readers' layout message never suggests
  the migration.
- `shared-contract`: the CLI manifest declares which commands skip the format check, and a refusal exits 2.

## Impact

- `shared/`: `config.yaml` (`format`), `cli.yaml` (exemptions, exit maps, `la-arch-migrate` help), `findings.yaml`,
  `schema/living-architecture.schema.json`; re-vendored into both twins (new contract hash).
- Python twin `python/src/living_architecture/{config,cli,c4,doctor}` and npm twin `node/src/{config,cli,c4,doctor}`.
- `architecture/model.c4` gains `c4 -> config` in both roots; `architecture/system.arc42.md` diagrams regenerated;
  `architecture/index.yaml` `repo-config` touches gain `python.cli` and `python.c4`.
- Conformance runner (`<FORMAT>` placeholder), every fixture config, re-blessed goldens that echo the config, new
  cases, `INVENTORY.md`.
- `plugin/skills/{init,living-architecture}/SKILL.md`, `docs/{configuration,commands,development}.md`.
- Adopter repos run `la-arch-migrate` once after upgrading; every command refuses until they do.
