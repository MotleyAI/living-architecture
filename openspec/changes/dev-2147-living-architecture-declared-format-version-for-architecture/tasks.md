## 1. Tests (pr-tests stage; failing until implemented)

- [x] 1.1 Conformance runner: substitute `<FORMAT>` (the bundled `shared/config.yaml` `format`) in root
  `living-architecture.yaml` overlays and `write:` steps only; README line. Runner unit tests prove other files and
  unrelated `<FORMAT>` text stay untouched. Verify the runner tests pass.
- [x] 1.2 Add `format: <FORMAT>` to every fixture/case `living-architecture.yaml` that is not itself a format case;
  goldens that echo the config get a version-agnostic `{pattern, replace}` normalization (never a blanket `0.4.0`
  replacement: the package version is also `0.4.0`). Verify with `rg -L '^format:' -g living-architecture.yaml conformance`.
- [x] 1.3 Neutral conformance cases for "Every command checks the declared format" (repo-config delta): newer
  (`9.0.0`) through `la-arch-check`, `la-arch-diagrams`, `la-config`; older (`0.3.0`) and missing through the same
  three; newer plus an unknown key; very large components; invalid values (`0.4`, `v0.4.0`, `0.04.0`, null, `true`,
  list, mapping); no committed file (with and without the local file); malformed YAML keeps its old error; `--help` and
  a usage error in an unversioned repo; an exempt review shim in an unversioned repo; current format passes. Each in
  `conformance/INVENTORY.md`.
- [x] 1.4 Conformance cases for "la-doctor reports the format check": newer with unknown key, older, missing with
  `--require-config`, missing plus `--expect` mismatch.
- [x] 1.5 Conformance cases for `format` in the local file (`la-config show` exit 1 naming `format`), `la-config get
  format`, and the updated defaults golden (`format: null`; re-bless reason: new key).
- [x] 1.6 Conformance cases for "la-arch-migrate converts the repo to the current format" and the modified legacy
  requirement (c4-layout delta): every scenario, including unversioned canonical / no model / index without a model /
  legacy (multi-file, single, no views) / non-migratable, no config, current, newer, invalid, unknown older,
  malformed YAML and scalar/list top levels, schema errors not blocking, stamp placement (comments, `%YAML`+`---`, CRLF,
  empty, comment-only without final newline), flow-style refusal, stamped repo passes `la-config show`.
  Existing migrate cases get an unversioned config.
- [x] 1.7 Reader case: a current-format repo with a legacy-shaped layout → merge-by-hand message without
  `la-arch-migrate`; existing "legacy layout points to the migration" goldens updated (reason: deliberate change).
- [x] 1.8 Twin unit tests (both twins): rollback on a failure injected at each step (create, delete, rmdir, config
  replace) leaves every path byte-identical; a failed restore is named in the message; version comparison
  (digit-count then lexical, huge components); stamp placement and verification; every non-exempt manifest command
  exits 2 with the missing-format message and every exempt one does not (parametrised over `shared/cli.yaml`, real
  argv per command); current format <= each package version and the `plugin.json` version.
- [x] 1.9 Codex review of the tests against this change (pr-tests Step 2); resolve findings with the user.

## 2. shared/

- [x] 2.1 `config.yaml`: `format: 0.4.0` with a one-line comment (the repo format this la reads and writes: the la
  version that introduced it).
- [x] 2.2 `schema/living-architecture.schema.json`: `format`, `["string","null"]`, default null, the version pattern
  anchored at both ends; the local schema does not gain it.
- [x] 2.3 `cli.yaml`: header documents `format: exempt` and "a format refusal exits 2"; mark `la-arch-migrate`,
  `la-doctor` and every review shim exempt; every gated command's exit map mentions the refusal under 2;
  `la-arch-migrate` help: "Convert the repo to the current format (`format` in living-architecture.yaml): for a repo
  that predates the key, merge a legacy architecture/model/*.c4 model into architecture/model.c4 (creating an empty
  architecture/views.c4 when absent), then stamp the format. Verified; writes everything or nothing and prints each
  written and deleted path." and its exit map (2 adds no config, newer, invalid or unknown format).
- [x] 2.4 `findings.yaml`: `format.missing`, `format.invalid` (value rendered with the shared renderer), `format.newer`,
  `format.older`, `arch-migrate.no-config`, `arch-migrate.unknown-format`, `arch-migrate.stamp-mismatch`,
  `arch-migrate.rollback-failed`; reword `arch-migrate.nothing` to name the format; remove `c4-layout.migrate`.
- [x] 2.5 `scripts/sync-shared`; verify the drift tests pass.

## 3. Python twin

- [x] 3.1 `config`: current-format accessor, version comparison, `check_format(root)` (lenient read, rules per spec),
  declared-format read and verified `stamp_format(text)`; `LaConfig` gains `format`. Verify the 1.8 unit tests.
- [x] 3.2 `cli`: one dispatch helper every wrapper calls — parse → root → format check (unless exempt) → handler.
  Verify the manifest-parametrised gate test.
- [x] 3.3 `c4/migrate.py`: the format flow, the unversioned detection (including "no index and no LikeC4 source"),
  the write protocol (exclusive creates, deletes, config replaced last via temp file + rename, reverse rollback,
  failed restores named). Verify the migrate cases and rollback tests.
- [x] 3.4 `c4/layout.py`: the readers' message always ends with the merge-by-hand tail; `legacy` state kept for
  migrate. Verify the layout cases.
- [x] 3.5 `doctor`: format check first; on refusal skip the config-dependent checks. Verify the doctor cases.
- [x] 3.6 `uv run pytest -q`, `ruff check src tests`, `basedpyright src tests` green in `python/`.

## 4. npm twin

- [x] 4.1 `node/src/config`: the same as 3.1, comparison without `Number`. Verify the twin unit tests.
- [x] 4.2 `node/src/cli`: format check after parsing and root resolution, before forwarding, scripts and handlers;
  exempt per manifest. Verify the gate test.
- [x] 4.3 `node/src/c4/{migrate,layout}.ts` and `node/src/doctor`: as 3.3–3.5.
- [x] 4.4 `npm run lint && npm run typecheck && npm test`, `npm run build && npm run conformance`, and
  `scripts/conformance-cross` green.

## 5. Architecture (approved edits only)

- [x] 5.1 `architecture/model.c4`: add `c4 -> config` after `c4 -> contract` in both the `python` and `typescript`
  roots; run `la-arch-diagrams` so `architecture/system.arc42.md` gains exactly `c4 --> config` in each mermaid block.
- [x] 5.2 `architecture/index.yaml`: `repo-config` touches gain `python.cli` and `python.c4`.
- [x] 5.3 `la-arch-check` green from either twin.

## 6. Skills and docs (skill wording approved; apply verbatim)

- [x] 6.1 `plugin/skills/init/SKILL.md`:
  - Preflight, replace "…unless the only failure is the existing `living-architecture.yaml` being invalid, which this
    skill converts (step 1)." with "…unless the only failure is the existing `living-architecture.yaml` being invalid
    or declaring an older format, which this skill converts (steps 1 and 5)."
  - Step 1 "Existing config": replace "Read it as raw YAML, not with `la-config` (which rejects removed keys)." with
    "Read it as raw YAML, not with `la-config` (which rejects removed keys and an older format)."
  - Step 2: append "Leave out `format`: step 5 stamps it."
  - Step 5, first sentence: "Write `living-architecture.yaml` at the repo root, with the flags matching the disk
    (`architecture: false` until `la:arch-init` finishes), then run `la-arch-migrate`: it stamps the current `format`
    and converts an older repo. Check it with `la-config show`."
- [x] 6.2 `plugin/skills/living-architecture/SKILL.md`:
  - Tree line: "`living-architecture.yaml           # repo config: format, and architecture: true once the model exists`"
  - Replace "A repo on the legacy `architecture/model/*.c4` layout converts with `la-arch-migrate` (verified,
    all-or-nothing)." with "The repo's format is `format` in `living-architecture.yaml`: the `la` version that
    introduced it. Every command refuses any other format, naming the `la` to upgrade to for a newer one and
    `la-arch-migrate` for an older or missing one; `la-arch-migrate` converts the repo (verified, all-or-nothing) and
    stamps the current format."
- [x] 6.3 `docs/configuration.md`: `format` line in the YAML block, a short "Format" section, "every key but `format`
  is optional" for committed files; `docs/commands.md` `la-arch-migrate` row; `docs/development.md`: a format change
  sets `format` in `shared/config.yaml` to its release version. Verify `npx -y @anthropic-ai/claude-code plugin
  validate plugin` and the skills test.

## 7. Versions and this repo

- [x] 7.1 Version 0.4.0 in `python/pyproject.toml`, `node/package.json`, `plugin/.claude-plugin/plugin.json`
  (`uv version 0.4.0`, lockfiles refreshed). Verify the version tests.
- [x] 7.2 Run `la-arch-migrate` on this repo, and add `format: 0.4.0` by hand to
  `acceptance/node-only/repo/living-architecture.yaml` (its index.yaml has no model yet, which
  `la-arch-migrate` refuses); verify each `living-architecture.yaml` gains only `format: 0.4.0`
  and `la-doctor --require-config` is healthy.
- [x] 7.3 Comment on DEV-2139 recording the ordering (this change is format 0.4.0; DEV-2139 becomes format 0.5.0 with a
  step keyed on declared `0.4.0`; its frozen plan needs the user's approval for that edit on its branch).
- [x] 7.4 Full suites of both twins and the cross-twin conformance run green.
