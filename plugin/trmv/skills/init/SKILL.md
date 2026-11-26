---
name: init
description: Onboard a repo to the trmv plugin — detect its test and type-check commands and the paths that are not its own source, propose trmv's config with a source for every key, write it, then offer the type-check baseline. Also the fast path other trmv skills run when a repo has no config, and the steps another plugin's onboarding uses for trmv's keys.
---

**Preflight:** run `trmv-doctor --plugin <this skill's base directory>` once per session before using any `trmv-*` command; if it fails, stop and show the user its output — unless the only failure is the config this skill writes being missing or invalid. If `trmv-doctor` is not found, or reports the trmv tools older than the plugin, stop and give the user the install command at this plugin's `version` (in its `.claude-plugin/plugin.json`): la's install command when the repo has `living-architecture.yaml`, else `uv tool install type-rename-move==<version>` in a Python repo, `npm install -g type-rename-move@<version>` in a TS/JS repo.

# Onboard a repo to trmv

trmv reads one committed config file at the repo root: `trmv.yaml`, else `living-architecture.yaml`.
A repo that already has `living-architecture.yaml` keeps trmv's keys in it, so it has one file; both present is
refused. Keys and defaults are in `docs/configuration.md` of the plugin repo; `trmv-config show` prints the resolved
values.

**Fast path.** When another skill's preflight reports the missing config, run steps 1–4 only, then hand back to that
skill. A full run (the user invoked `/trmv:init`) continues to step 5.

**Stealth setup.** When the repo has no config, ask once (with PROS, CONS and a RECOMMENDATION) whether to set it up
in stealth mode: for a repo the user does not own, where nothing committed or pushed may show the tools were used. In
stealth mode step 3 writes `<C>/trmv/trmv.yaml` (`<C>` = `git rev-parse --path-format=absolute --git-common-dir`),
never a file at the repo root, and step 5 offers no baseline: `trmv-typecheck` compares with the merge base. Nothing
is committed. Details: `docs/configuration.md`, "Stealth mode".

## 1. Detect

Read, don't ask. For each key note the value and where it came from:

- **Existing config.** If `trmv.yaml` or `living-architecture.yaml` exists, this run edits trmv's keys
  in it in place: start from their values and leave every other key alone. Read it as raw YAML, not with
  `trmv-config`, which rejects an invalid file.
- **`commands.test`.** From the package manifests (`trmv-config get lang.<language>.markers`), a `Makefile`, the CI
  workflows and `CLAUDE.md`/`AGENTS.md`. It must be the full non-integration suite: the refactor gate runs it.
- **`commands.typecheck`.** Each language's checker. Propose an entry only where the default
  (`trmv-config get commands.typecheck.<language>`) does not fit — a subdirectory project, or `null` for a checker that
  is not compatible with the default (the language docs in `<this skill's base directory>/../../languages/` give
  examples).
- **`exempt`.** Propose globs for generated or vendored code and fixtures you find.
- **`refactor`.** Keep the defaults unless the repo's own instructions say otherwise.

## 2. Propose

Show trmv's proposed keys, each on its own line with a trailing comment naming its source (`# detected: Makefile`,
`# default`, `# your answer`). Omit keys whose value equals the default only when the source is `default`. Leave out
`format`: step 3 adds it. Ask only about keys you could not detect, in one message.

## 3. Write the file

Write trmv's keys into the existing config file, or into a new `trmv.yaml` at the repo root when
there is none. A new `trmv.yaml` starts with the line `format: <version>`, where `<version>` is the
format `trmv-doctor --require-config` names when the file declares none. Check it with `trmv-config show`.

## 4. Doctor

Run `trmv-doctor --plugin <this skill's base directory> --require-config`. Fix whatever it reports (an invalid value, a
missing checker) and re-run until it passes.

## 5. Type-check baseline (full run only)

If `trmv-typecheck` checks a language that has no baseline yet, offer (yes/no) `trmv-typecheck --write-baseline`. This is
the one legitimate recording: afterwards the baseline only shrinks.

Never wire CI. Do not commit: the user commits the config.
