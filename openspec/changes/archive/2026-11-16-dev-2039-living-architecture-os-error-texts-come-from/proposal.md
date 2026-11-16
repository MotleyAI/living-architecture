## Why

The first pass at this issue (archived change `2026-10-03-dev-2039-living-architecture-os-error-texts-come-from-the-shared`)
let each twin pass its runtime's own OS and YAML error wording through. The twins therefore print different text for the
same failure, goldens can only check `contains:`, and several read failures crash instead of refusing: an unreadable or
non-UTF-8 config in every command, an unreadable `architecture/index.yaml` in the c4 readers and the TypeScript refactor
workspace. Principle 2 (user-facing texts come only from the shared contract) and principle 1 (twins) are both broken.

## What Changes

- New `shared/findings.yaml` templates for OS errors (`os.*`, keyed by the portable symbolic error code, path and reason
  separate) and for invalid YAML (`yaml.invalid`, `yaml.invalid-because`). Both twins render every OS error and every
  non-duplicate-key YAML error from them; no runtime wording and no errno number reaches output.
- One renderer and one existence probe per twin, in `contract`. Only `ENOENT` means "absent" for the config files and
  `architecture/index.yaml`; any other stat or read error is reported, never treated as absence, never a crash.
- The config loaders (load and format check, both twins) turn OS, decode and YAML errors into config errors, so every
  command that loads the config refuses instead of crashing, and `dr-refactor` treats an unreadable config exactly
  as an invalid one.
- The c4 index readers, the archcheck index loader, the TypeScript refactor workspace and `la-doctor` report an
  unreadable index from the templates.
- The conventions gate's `[unreadable]` finding prints the template reason; the PyPI twin's invalid UTF-8 uses the
  existing `conventions.not-utf8` text, as the npm twin already does.
- The conformance contract no longer excludes runtime-supplied error detail from byte comparison; goldens that checked
  OS or YAML errors with `contains:` become byte-exact, and new cases pin every OS error kind through `la-arch-check`
  and `la-arch-diagrams`.
- `shared/` changes, so the contract hash changes.

## Capabilities

### New Capabilities

### Modified Capabilities
- `shared-contract`: "Observable outputs reproduce the conformance goldens" is replaced by "... byte for byte", which
  no longer excludes runtime error detail from byte comparison (OpenSpec cannot drop a scenario from a MODIFIED
  requirement, so it is removed and re-added); a new requirement that OS and YAML errors render from the shared
  registry; the `la-arch-check` invalid-YAML scenario of the duplicate-key requirement prints the template text.

## Impact

- `shared/findings.yaml`, a new shared vector file for OS error rendering, every twin snapshot (`scripts/sync-shared`).
- PyPI twin: `contract`, `config/load.py`, `config/format.py`, `c4/index.py`, `c4/diagrams.py`, `c4/migrate.py`,
  `archcheck/index.py`, `archcheck/__init__.py`, `archcheck/scaffold.py`, `affected`, `lang/source.py`,
  `lang/language_server.py`, `typecheck`, `doctor`.
- npm twin: `contract` (renderer, probe, `readFile`), every target-repo `readFileSync` call site, `eslint.config.mjs`,
  `config/index.ts`, `config/format.ts`, `c4/index-file.ts`, `c4/diagrams.ts`, `c4/migrate.ts`,
  `archcheck/index-file.ts`, `archcheck/index.ts`, `affected`, `lang/conventions.ts`, `refactor/workspace.ts`, `doctor`.
- `conformance/cases/` (new and converted cases), `conformance/INVENTORY.md`.
- No model or arc42 change: every touched element already depends on `contract`.
