## 1. Contract (pr-tests)

- [ ] 1.1 Add the `os.*` / `yaml.*` templates of design.md decision 3 to `shared/findings.yaml` (new section after `yaml.duplicate-key`); run `scripts/sync-shared`; verify `scripts/sync-shared --check` passes
- [ ] 1.2 Add `shared/vectors/os-errors.yaml`: cases (symbolic code, exception path or none, explicit path or none, root) → expected text, covering each of the four kinds, `os.other` with a code and with none, explicit path overriding the exception's, a path under the root, equal to the root's child, outside the root, relative to cwd, and no path at all (reason alone); sync; verify the drift test passes
- [ ] 1.3 Unit tests in both twins running every `os-errors.yaml` vector through the renderer (fail until 3.1 / 4.1)
- [ ] 1.4 Unit tests in both twins for the `contract` existence probe: regular file true, missing false, non-regular false, `ENOTDIR` / `EACCES` / `ELOOP` raise (fail until 3.1 / 4.1)
- [ ] 1.5 npm unit test for `readFile`: a directory raises `EISDIR` carrying the path; both overloads return `Buffer` / `string` (fails until 4.1)

## 2. Conformance (pr-tests)

New cases, each listed in `conformance/INVENTORY.md`; exact goldens unless noted:

- [ ] 2.1 `arch-check-index-permission-denied` (neutral; `chmod: {architecture/index.yaml: '0000'}`): exit 2, `arch_check: architecture/index.yaml: permission denied`
- [ ] 2.2 `arch-check-index-is-directory` (neutral; `architecture/index.yaml/.keep`): exit 2, `arch_check: architecture/index.yaml: is a directory`
- [ ] 2.3 `arch-check-index-not-a-directory` (neutral; `architecture` a regular file): exit 2, `arch_check: architecture/index.yaml: not a directory`. Calibration: confirm `la-arch-check` reads the index before any layout check of `architecture/`; if another message comes first in either twin, STOP and ask (the scenario would change)
- [ ] 2.4 `arch-check-index-loop` (neutral; `symlinks: {architecture/index.yaml: index.yaml}`): exit 2, `arch_check: architecture/index.yaml: OS error ELOOP`
- [ ] 2.5 `arch-diagrams-doc-permission-denied` (neutral; fixture `arch-diagrams`, chmod a mapped doc `0000`): exit 1, `la-arch-diagrams: <doc>: permission denied`, docs unchanged (`files:`)
- [ ] 2.6 `arch-diagrams-index-not-a-directory` (neutral; `architecture` a regular file): exit 1, `la-arch-diagrams: architecture/index.yaml: not a directory`; same calibration as 2.3 against the layout check
- [ ] 2.7 `arch-diagrams-index-untraversable` (neutral; `chmod: {architecture: '0000'}`): exit 1, `la-arch-diagrams: architecture/index.yaml: permission denied`
- [ ] 2.8 `arch-migrate-index-untraversable` (neutral; legacy-format repo, `chmod: {architecture: '0000'}`): exit 2, `la-arch-migrate: architecture/index.yaml: permission denied`, `living-architecture.yaml` and every file unchanged (`files:`)
- [ ] 2.9 `config-unreadable` (neutral; `chmod: {living-architecture.yaml: '0000'}`, `la-config show`): exit 1, `la-config: living-architecture.yaml: permission denied`
- [ ] 2.10 `config-not-utf8` (neutral; `la-config show`): exit 1, `la-config: living-architecture.yaml: invalid YAML`
- [ ] 2.11 `refactor-config-permission-denied` (paired python/typescript, a dry-run `dr-refactor` rename on a minimal fixture, config chmod `0000`): golden equals the same run with an invalid-YAML config, no traceback. Note in the case: PR #49 (DEV-2302) makes `dr-refactor` refuse in `checks` with exit 2 for an unusable config; whichever of the two PRs merges second re-blesses this golden
- [ ] 2.12 `refactor-ts-index-unreadable` (adapter typescript; index chmod `0000`, a TS rename): exit 2, `architecture/index.yaml: permission denied`, nothing written
- [ ] 2.13 `conventions-ts-unreadable-directory` (adapter typescript; a changed `.ts` path that is a directory): `src/<x>.ts:1: [unreadable] is a directory`
- [ ] 2.14 `doctor-index-not-a-directory` (neutral; `architecture: true` config, `architecture` a regular file): exit 1, a problem line `architecture/index.yaml: not a directory`

Converted to exact goldens (commit reason: deliberate behaviour change, OS/YAML texts now come from the contract). Remove each "wording is not contract" note; `golden: manual` cases are edited by hand, the rest written with `LA_UPDATE_GOLDENS=1`:

- [ ] 2.15 `arch-check-index-missing` → `arch_check: architecture/index.yaml: no such file or directory`
- [ ] 2.16 `arch-diagrams-doc-missing` → `la-arch-diagrams: architecture/gone.arc42.md: no such file or directory`
- [ ] 2.17 `arch-diagrams-doc-is-directory` → `la-arch-diagrams: architecture/gone.arc42.md: is a directory`
- [ ] 2.18 `conventions-unreadable-directory` → `src/pkg.py:1: [unreadable] is a directory`
- [ ] 2.19 `conventions-unreadable-binary` → `src/bin.py:1: [unreadable] not valid UTF-8`
- [ ] 2.20 `arch-check-index-invalid-yaml` → `arch_check: architecture/index.yaml: invalid YAML`
- [ ] 2.21 `config-error-invalid-yaml`, `config-error-refused-tag`, `config-error-impossible-date` → `la-config: living-architecture.yaml: invalid YAML`
- [ ] 2.22 `arch-migrate-config-invalid-yaml`, `arch-migrate-config-not-utf8` → exact stderr from `yaml.invalid`
- [ ] 2.23 Verify the template-registry test sees every new template produced by a golden (`yaml.invalid-because` by the existing config duplicate-key cases); verify no golden under `conformance/cases/` contains `[Errno`

## 3. PyPI twin (pr-implement)

- [ ] 3.1 `contract`: the renderer (full and reason-only forms) and the existence probe per design.md 5–6; verify 1.3 / 1.4 pass
- [ ] 3.2 `config/load.py` `_raw` and `config/format.py`: probe, OS → `ConfigError(os.error)`, decode/YAML → `yaml.invalid`, duplicate key → `yaml.invalid-because`; path is the config file's name; verify 2.9, 2.10, 2.21, 2.22
- [ ] 3.3 `c4/index.py`: probe; stat/read error → `os.error` message for `architecture/index.yaml`; verify 2.7, 2.8
- [ ] 3.4 `archcheck/index.py`: OS → `os.error`, non-duplicate YAML → `yaml.invalid`; catch-alls in `archcheck/__init__.py`, `archcheck/scaffold.py`, `c4/diagrams.py`, `c4/migrate.py`, `affected` → the renderer with the repo root; verify 2.1–2.6, 2.15–2.17, 2.20
- [ ] 3.5 `lang/source.py`: OS → reason only; `UnicodeDecodeError` → `conventions.not-utf8`; verify 2.18, 2.19
- [ ] 3.6 `typecheck` checker launch and `lang/language_server.py` launch: `os.error` with the command as path; unit tests for both
- [ ] 3.7 `doctor`: config/index checks through the probe, an `OSError` → a problem line; plugin walk unchanged; verify 2.14

## 4. npm twin (pr-implement)

- [ ] 4.1 `contract`: renderer, probe and `readFile` per design.md 5–7; verify 1.3–1.5 pass
- [ ] 4.2 Replace every target-repo `readFileSync` in `node/src` with `readFile`; keep stdin, snapshot and package-version reads with a line-level eslint-disable and reason; add the `readFileSync` import restriction to `eslint.config.mjs`; verify `npm run lint`
- [ ] 4.3 `config/index.ts` `raw` and `config/format.ts`: as 3.2
- [ ] 4.4 `c4/index-file.ts`: as 3.3; `refactor/workspace.ts` `namedConfig`: probe, read error → `RefactorError(os.error)`; verify 2.12
- [ ] 4.5 `archcheck/index-file.ts`, `archcheck/index.ts` `setupErrorText`, `c4/diagrams.ts`, `c4/migrate.ts`, `affected`: as 3.4
- [ ] 4.6 `lang/conventions.ts` `fileFacts`: OS → reason only; verify 2.13
- [ ] 4.7 `doctor`: as 3.7

## 5. Audit and gate

- [ ] 5.1 Audit both twins for every remaining observable `str(exc)` / `error.message` of an OS or YAML error (grep `OSError`, `ErrnoException`, `.message`, `str(exc)`); map each to the renderer or to an existing non-OS template; record any site left as is with its reason in this task
- [ ] 5.2 `python/`: the affected tests (per the flow's local test scope), `uv run ruff check src tests`, `uv run basedpyright src tests`
- [ ] 5.3 `node/`: `npm run lint && npm run typecheck`, the affected tests, `npm run build && npm run conformance`
- [ ] 5.4 `scripts/conformance-cross`, `scripts/sync-shared --check`, `la-arch-check`
