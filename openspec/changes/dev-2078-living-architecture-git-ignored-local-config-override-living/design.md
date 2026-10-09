## Context

- **Readers of the committed file.** Today `load_config` (Python `config/load.py`, npm `config/index.ts`) and
  `explicit_typecheck` / `explicitTypecheck` each read it on their own.
- **Hard-coded file name.** `CONFIG_FILENAME` is a constant in both twins.
- **Validators.** They compile one schema at a time: Python `jsonschema.Draft202012Validator` with no
  registry, npm Ajv 2020 (`strict: false`) cached by the schema's JSON text. No shared schema uses a
  cross-file `$ref` yet.
- **Doctor.** `_config_problems` / `configProblems` returns early when the committed file is absent.

**Architecture.** The change touches `config`, `doctor` and `contract` in both twins and adds no new edge.
- `doctor → config` and `config → contract` already exist.
- The spec stays under the cross-cutting `repo-config` entry, which touches `python.config` and
  `python.doctor`.
- Principles of `architecture/system.arc42.md`:
  - **P1:** both twins behave identically, proved by neutral conformance cases.
  - **P2:** the allowlist, both file names and every text come from `shared/`.
  - **P4:** only `git` runs, never target-repo code.

## Goals / Non-Goals

**Goals:** see the repo-config and shared-contract delta specs.

**Non-Goals:**
- No environment variable.
- No local file outside the repo root.
- `/la:init` never writes a local file.
- No version bump in this change.
- A non-regular entry at either config path keeps counting as absent: no new error for directories or
  unreadable entries.

## Decisions

### D1. Allowlist: `tracker` and `reviewers.codex`, as a separate local schema with cross-file `$ref`s
`shared/schema/living-architecture.local.schema.json`:
- The `tracker` property is `{"$ref": "living-architecture.schema.json#/properties/tracker"}`.
- `reviewers` holds only `codex`, a `$ref` to `.../properties/reviewers/properties/codex`.
- `additionalProperties: false` at both levels.

**Alternatives:**
- **Every key overridable:** rejected by the user. It would let a contributor diverge from gates that CI
  enforces and from the disk checks.
- **Annotate the main schema and prune it in code:** duplicates JSON Schema semantics in both twins.
- **A copied local schema:** drifts.

**Why `$ref`:** the validators already implement JSON Schema, so referencing is generic infrastructure.

### D2. A schema store keyed by `$id`
- Each twin's `contract` loads every shared schema once and registers each under its `$id`:
  - Python: a `referencing.Registry` passed to the validator.
  - npm: one Ajv instance with `addSchema` for each schema.
- `validate` takes the target schema and resolves references against the store. On Ajv, it fetches the
  already-added schema with `getSchema($id)` instead of compiling it again, which avoids a duplicate-`$id`
  error.
- Compiled validators are cached by `$id`.
- The existing validation suites (config, facts, index, node, conventions-facts) are the regression net, plus
  unit tests for the cross-file reference.

### D3. One raw loader for the merged data and its overrides
`config` gains one function per twin. It returns:
- the merged raw data: committed-or-`{}`, deep-merged with the local file;
- the overridden dotted leaf keys of the local file, in schema order;
- whether each file exists.

**Order of checks:**
1. committed YAML
2. local YAML
3. the local top level is a mapping
4. the local schema; errors are prefixed with the local path
5. the merge
6. `resolve`, whose errors are prefixed with the committed path

A local value valid under D1 cannot break the full schema, so step 6 errors always belong to the committed
file.

**Users:** `load_config` and `explicit_typecheck` both use it, so no second reader can drift. The deep merge
recurses on mappings and replaces anything else; null is a replacing value, but D1 rejects it for both keys.

### D4. Provenance is a stderr note on `show` only
- **Stdout** keeps the resolved JSON, so every existing `show` golden stands and `show`/`get` keep one meaning.
- **Template** `config.local-override: 'la-config: {key} from {file}'`, one line per overridden key in schema
  order, emitted even when the value equals the committed one.
- **`get`:** prints no note, so `$(la-config get …)` stays clean.

### D5. Doctor
- **Config validation:** runs whenever either file exists.
- **Consistency and `--require-config`:** stay gated on the committed file, but consistency evaluates the
  merged config.
- **Git state** (only inside a git repo and when the local file exists):
  - `git ls-files -z -- <local>`: non-empty output means tracked (staged included) → `doctor.local-tracked`.
  - Otherwise `git check-ignore -q -- <local>`: exit 1 → `doctor.local-not-ignored`.
  - Any non-zero `ls-files` status, or any `check-ignore` status other than 0/1 → `doctor.local-git-failed`.
- **Placement:** this finding comes after the config/consistency findings and before the missing
  executables.
- **Ok line:** the source becomes `doctor.local-source: '{source} + {local}'` when the local file exists, with
  `{source}` today's committed-file name or the defaults text.

**New finding texts:**
- `doctor.local-tracked: '{file} is tracked by git, but it holds one contributor''s overrides; run git rm --cached {file} and add it to .gitignore'`
- `doctor.local-not-ignored: '{file} is not git-ignored; add it to .gitignore'`
- `doctor.local-git-failed: 'git failed, so whether {file} is git-ignored cannot be checked'`

### D6. File names in `shared/config.yaml`
- `file: living-architecture.yaml` and `local_file: living-architecture.local.yaml`, following the precedent of
  `shared/architecture.yaml`.
- Each twin's `contract` exposes accessors, which replace the hard-coded constant everywhere a path or
  source label is built.
- `doctor.config-missing` keeps its literal sentence.

### D7. `/la:init` wording (approved)
- **Step 1, end of the "Existing config" bullet:** "`living-architecture.local.yaml`, if present, holds one
  contributor's overrides; never fold its values into the committed file."
- **Step 5, appended:** "If `git check-ignore -q living-architecture.local.yaml` exits 1 (not ignored), offer
  (yes/no) to add `living-architecture.local.yaml` to `.gitignore`: it holds per-person overrides and must
  never be committed."
- A tracked local file, or a git failure, is left to step 6's `la-doctor`, which reports it with its own
  remedy.

## Risks / Trade-offs

- [Ajv and jsonschema word `$ref` failures differently] → Config-error wording is not contract; the
  conformance cases pin only the exit code and the named key and file (`stderr: contains`).
- [Changing the schema-store plumbing could alter unrelated validation] → The existing facts, index, node and
  conventions-facts suites run unchanged, and the store only adds resolvable resources.
- [A contributor leaves the local file unignored and commits it] → `la-doctor` (run by every skill's
  preflight) fails until it is ignored or untracked, and `/la:init` offers the ignore entry.
- [Notes on stderr are lost when `show` is redirected] → Accepted: stdout is the configuration, and the
  provenance is for the human at the terminal.
