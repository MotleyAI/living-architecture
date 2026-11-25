---
name: init
description: Onboard a repo to the dr plugin — detect its test and type-check commands and the paths that are not its own source, propose dr's config with a source for every key, write it, then offer the type-check baseline. Also the fast path other dr skills run when a repo has no config, and the steps another plugin's onboarding uses for dr's keys.
---

**Preflight:** run `dr-doctor --plugin <this skill's base directory>` once per session before using any `dr-*` command; if it fails, stop and show the user its output — unless the only failure is the config this skill writes being missing or invalid.

# Onboard a repo to dr

dr reads one committed config file at the repo root: `deterministic-refactor.yaml`, else `living-architecture.yaml`.
A repo that already has `living-architecture.yaml` keeps dr's keys in it, so it has one file; both present is
refused. Keys and defaults are in `docs/configuration.md` of the plugin repo; `dr-config show` prints the resolved
values.

**Fast path.** When another skill's preflight reports the missing config, run steps 1–4 only, then hand back to that
skill. A full run (the user invoked `/dr:init`) continues to step 5.

## 1. Detect

Read, don't ask. For each key note the value and where it came from:

- **Existing config.** If `deterministic-refactor.yaml` or `living-architecture.yaml` exists, this run edits dr's keys
  in it in place: start from their values and leave every other key alone. Read it as raw YAML, not with
  `dr-config`, which rejects an invalid file.
- **`commands.test`.** From the package manifests (`dr-config get lang.<language>.markers`), a `Makefile`, the CI
  workflows and `CLAUDE.md`/`AGENTS.md`. It must be the full non-integration suite: the refactor gate runs it.
- **`commands.typecheck`.** Each language's checker. Propose an entry only where the default
  (`dr-config get commands.typecheck.<language>`) does not fit — a subdirectory project, or `null` for a checker that
  is not compatible with the default (the language docs in `<this skill's base directory>/../../languages/` give
  examples).
- **`exempt`.** Propose globs for generated or vendored code and fixtures you find.
- **`refactor`.** Keep the defaults unless the repo's own instructions say otherwise.

## 2. Propose

Show dr's proposed keys, each on its own line with a trailing comment naming its source (`# detected: Makefile`,
`# default`, `# your answer`). Omit keys whose value equals the default only when the source is `default`. Leave out
`format`: step 3 adds it. Ask only about keys you could not detect, in one message.

## 3. Write the file

Write dr's keys into the existing config file, or into a new `deterministic-refactor.yaml` at the repo root when
there is none. A new `deterministic-refactor.yaml` starts with the line `format: <version>`, where `<version>` is the
format `dr-doctor --require-config` names when the file declares none. Check it with `dr-config show`.

## 4. Doctor

Run `dr-doctor --plugin <this skill's base directory> --require-config`. Fix whatever it reports (an invalid value, a
missing checker) and re-run until it passes.

## 5. Type-check baseline (full run only)

If `dr-typecheck` checks a language that has no baseline yet, offer (yes/no) `dr-typecheck --write-baseline`. This is
the one legitimate recording: afterwards the baseline only shrinks.

Never wire CI. Do not commit: the user commits the config.
