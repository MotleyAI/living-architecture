## Why

`load_config` reads only the committed `living-architecture.yaml`, so a contributor who lacks the repo's
tracker or reviewers cannot get through the flow. For example, an outside contributor to a repo with
`tracker: linear` and `reviewers.codex: true` has no Linear access and no Codex server, and `pr-plan` stops.
The only workaround is an uncommitted edit to a tracked file, which is easy to commit by accident.

## What Changes

- **Local override file**: an optional, git-ignored `living-architecture.local.yaml` at the repo root. It may
  set only the per-person keys `tracker` and `reviewers.codex`; any other key is a config error naming that
  key. It is deep-merged over the committed file (or over the defaults when there is none), and the result
  is resolved and validated exactly like the committed file today. Every command that reads the config sees
  the merged result.
- **`la-config show`**: stdout stays the resolved configuration as JSON. stderr gets one note per key the
  local file sets, naming the file, in schema order. `la-config get` is unchanged.
- **`la-doctor`**:
  - It validates the merged config whenever either file exists.
  - Its config/disk consistency checks run on the merged config, still only when the committed file exists.
  - A local file alone does not onboard a repo: `--require-config` still reports the missing committed file.
  - Inside git, it reports a local file that git tracks (staged included) or does not ignore, or a git
    failure while checking.
  - Its ok line names the local file as a second source.
- **Shared contract**:
  - A new local-file schema references the main schema's definitions of the two overridable keys.
  - Both file names move into a new `shared/config.yaml`.
  - The schema validators of both twins resolve cross-file `$ref`s.
  - New finding templates: the show note, three doctor findings, and the ok-line source.
- **`/la:init`**: it never folds the local file's values into the committed file, and it offers to add the
  local file to `.gitignore` when git does not ignore it.
- **Docs**: a "Local overrides" section in `docs/configuration.md` and the `la-config` row of
  `docs/commands.md`. This repo's `.gitignore` ignores the local file.

## Capabilities

### New Capabilities

### Modified Capabilities
- `repo-config`:
  - A new requirement for the local override file (allowed keys, merge, validation, provenance notes).
  - A new requirement for the doctor's git-state checks on it.
  - The doctor's config/disk consistency and `--require-config` requirements now say how the local file
    takes part.
- `shared-contract`: the configuration-parameters requirement also covers the local file's allowed keys
  (the local schema) and the config file names.

## Impact

- `shared/`:
  - new `schema/living-architecture.local.schema.json`
  - new `config.yaml`
  - `findings.yaml` (`config.local-override`, `doctor.local-tracked`, `doctor.local-not-ignored`,
    `doctor.local-git-failed`, `doctor.local-source`)
  - Both snapshots are re-synced and the contract hash changes.
- Both twins: `config` (one raw loader for the merged data and its overridden keys, used by `load_config` and
  `explicit_typecheck`), `doctor`, and `contract` (schema store keyed by `$id`; accessors for the file names).
- `plugin/skills/init/SKILL.md`, `docs/configuration.md`, `docs/commands.md`, `.gitignore`.
- `conformance/cases/` (new neutral cases) plus `INVENTORY.md`; unit tests in both twins.
- No new import edges between nodes; the spec stays under the cross-cutting `repo-config` entry.
- Unblocks DEV-2076 (documenting the override for SLayer's outside contributors) once released.
