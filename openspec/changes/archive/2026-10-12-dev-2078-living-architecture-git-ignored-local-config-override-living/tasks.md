Before writing code, read `architecture/system.arc42.md` (principles P1, P2, P4), `architecture/model.c4` and
design.md. No new import edge is allowed. Any arc42 or model edit needs the user's OK on the exact wording.

## 1. Shared contract

- [x] 1.1 New `shared/schema/living-architecture.local.schema.json` per design D1 (cross-file `$ref`s to `tracker` and `reviewers.codex`, `additionalProperties: false` at both levels, `$id` set). Verify: the shared-contract "Local schema follows the main schema" scenario has unit tests in both twins.
- [x] 1.2 New `shared/config.yaml` with `file` and `local_file` (design D6). Verify: both twins' accessors return them, with unit tests.
- [x] 1.3 `shared/findings.yaml`: add `config.local-override`, `doctor.local-tracked`, `doctor.local-not-ignored`, `doctor.local-git-failed`, `doctor.local-source` with the wording in design D4/D5. Verify: 4.2 maps each to a golden.
- [x] 1.4 Run `scripts/sync-shared`. Verify: `scripts/sync-shared --check` exits 0 and the drift test passes.

## 2. Contract infrastructure (both twins)

- [x] 2.1 Schema store keyed by `$id` (design D2): Python `referencing.Registry`, npm one Ajv with `addSchema` + `getSchema`, compiled validators cached by `$id`. Verify: new unit tests validate the local schema through the cross-file `$ref` (valid value, enum violation, wrong type), and the existing facts/index/node/conventions-facts/config suites pass unchanged.
- [x] 2.2 Accessors for the two config file names from `config.yaml`; remove the hard-coded `CONFIG_FILENAME` value from both twins (everything that builds a config path or source label uses the accessors). Verify: no `living-architecture.yaml` literal remains in `python/src` or `node/src` outside the snapshot data (grep), and the suites pass.

## 3. Config and doctor (both twins)

- [x] 3.1 One raw loader (design D3) returning the merged data, the overridden dotted keys in schema order and which files exist; `load_config` and `explicit_typecheck` both use it. Verify: unit tests for the deep merge (sibling kept, scalar replaced), the override list order, and the order of checks (committed YAML, local YAML, local mapping, local schema with the local path, merged resolve with the committed path).
- [x] 3.2 `la-config show` prints one `config.local-override` note per overridden key on stderr; `get` prints none (design D4). Verify: the repo-config local-file scenarios through conformance (4.1).
- [x] 3.3 Doctor (design D5): validate whenever either file exists; consistency on the merged config, still gated on the committed file; `--require-config` ignores a local-only file; the git-state finding (tracked → not-ignored → git-failed) placed after config/consistency and before executables; the ok-line `doctor.local-source`. Verify: the doctor scenarios of both repo-config requirements through conformance (4.1), plus unit tests for the git-state branches.

## 4. Conformance

- [x] 4.1 New neutral cases (hand-written goldens, `golden: manual`), one per scenario:
  - `config-local-show-override`: both keys set locally, `tracker` equal to the committed value; stdout is the JSON, stderr exactly two notes in order.
  - `config-local-deep-merge`, `config-local-without-committed`, `config-local-empty`
  - `config-local-refused-top-key`, `config-local-refused-nested-key`, `config-local-invalid-value`, `config-local-invalid-yaml`, `config-local-top-level-list`: each with `stderr: contains` the key and the local file name.
  - `config-get-local-override`
  - `doctor-local-ignored-ok`, `doctor-local-tracked`, `doctor-local-staged`, `doctor-local-not-ignored`, `doctor-local-git-failed`, `doctor-local-not-git`, `doctor-local-consistency-merged`, `doctor-local-only-invalid`, `doctor-require-config-local-only`

  Verify: `uv run pytest -q` in `python/` and `npm run build && npm run conformance` in `node/` pass, and `scripts/conformance-cross` passes.
- [x] 4.2 List every new case in `conformance/INVENTORY.md`, and map each new `findings.yaml` template to at least one golden. Verify: the inventory and registry-coverage tests pass.

## 5. Skill, docs, this repo

- [x] 5.1 `plugin/skills/init/SKILL.md`: add exactly the two sentences approved in design D7 (step 1 bullet, step 5). Verify: `test_skills.py` passes; diff shows only those two additions.
- [x] 5.2 `docs/configuration.md`: new "Local overrides" section (file, allowlist, merge, stderr notes, doctor checks, `.gitignore`); `docs/commands.md`: the `la-config` row mentions the local file. Verify: the docs link tests pass.
- [x] 5.3 Add `living-architecture.local.yaml` to this repo's `.gitignore`. Verify: `git check-ignore -q living-architecture.local.yaml` exits 0.

## 6. Final gate

- [x] 6.1 Full suites of both twins, ruff, basedpyright, `npm run lint && npm run typecheck`, `scripts/sync-shared --check`, `scripts/conformance-cross`, `la-arch-check`, `npx -y @anthropic-ai/claude-code plugin validate plugin`, and `openspec validate dev-2078-living-architecture-git-ignored-local-config-override-living --strict`. Verify: all green.
