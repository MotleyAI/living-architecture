---
name: init
description: Onboard a repo to the la plugin — detect its tracker, test/lint/type-check commands, Codex, Sonar and any existing OpenSpec or architecture setup, propose a complete living-architecture.yaml with a source for every key, ask only what cannot be detected, write the file, then offer the type-check baseline and la:arch-init. Also the fast path other skills run when a repo has no config, and the way to edit or convert an existing config.
---

**Preflight:** run `la-doctor --plugin <this skill's base directory>` once per session before using any `la-*` or `dr-*` command; if it fails, stop and show the user its output — unless the only failure is the existing `living-architecture.yaml` being invalid, which this skill converts (step 1).

# Onboard a repo

`living-architecture.yaml` records each gate of the flow as an explicit decision; its presence means the repo
is onboarded. Keys, defaults and the doctor's consistency checks are in `docs/configuration.md` of the plugin
repo; `la-config show` prints the resolved values.

**Fast path.** When another skill's preflight reports the missing config, run steps 1–6 only, then hand back
to that skill. A full run (the user invoked `/la:init`) continues to step 7.

## 1. Detect

Read, don't ask. For each key note the value and where it came from:

- **Existing config.** If `living-architecture.yaml` exists, this run edits it in place: start from its
  values. Read it as raw YAML, not with `la-config` (which rejects removed keys). Under `reviewers`, the
  `coderabbit` flag and Sonar's `enabled` switch were removed (both bots are detected per PR): propose
  deleting them and keeping Sonar's `project_key`.
- **`tracker`.** `linear` when the Linear MCP server is available and branch names look like
  `<user>/<key>-<slug>` (`git branch -a`); `github` when branches look like `<N>-<slug>` or the repo uses
  GitHub issues (`gh issue list --limit 5`); otherwise undetected.
- **`issue_key_pattern`.** `#\d+` for `github`; the default for `linear`.
- **`openspec`.** `true` when `openspec/` exists; otherwise undetected (an opinion).
- **`architecture`.** `true` only when `architecture/index.yaml` exists; otherwise `false` (`la:arch-init`
  flips it when it finishes).
- **`reviewers.codex`.** Whether the Codex MCP server (`mcp__codex__codex`) is available in this session.
- **`reviewers.sonar.project_key`.** Only needed when it cannot be inferred: Sonar in CI
  (`.github/workflows/*`) with no `sonar-project.properties` key. `la-pr-reviewers <PR>` on a recent PR shows
  what is inferred.
- **`commands.test` / `commands.lint`.** From the package manifests (`la-config get lang.<language>.markers`, `package.json` scripts), a `Makefile`, the CI
  workflows and `CLAUDE.md`/`AGENTS.md`. The test command must be the full non-integration suite.
- **`commands.typecheck`.** Each language's checker. Propose an entry only where the default
  (`la-config get commands.typecheck.<language>`) does not fit — a subdirectory project, or `null` for a
  checker that is not compatible with the default (the language docs in `<this skill's base
  directory>/../../languages/` give examples).
- **`conventions`.** Keep the defaults unless the repo's own instructions say otherwise; propose
  `conventions.exempt` globs for generated or vendored code you find.

## 2. Propose

Show the complete proposed `living-architecture.yaml`, every key on its own line with a trailing comment
naming its source (`# detected: package.json`, `# default`, `# your answer`). Omit keys whose value equals
the default only when the source is `default`.

## 3. One question round

Ask, in one message, only about keys that are opinions or undetected: usually `openspec` when there is no
`openspec/`, `tracker` when undetected, and `reviewers.codex` when Codex is not available here. For each, give
the PROS and CONS of each option and a RECOMMENDATION. Never ask about a key you detected with confidence.
`tracker: none` with `openspec: false` leaves no place for the plan to survive a session reset: never
propose it.

## 4. OpenSpec scaffold

If the answer is `openspec: true` and `openspec/` is absent, run the `la:openspec-init` skill now, before
writing the file, so the flag matches the disk.

## 5. Write the file

Write `living-architecture.yaml` at the repo root, with the flags matching the disk (`architecture: false`
until `la:arch-init` finishes). Check it with `la-config show`.

## 6. Doctor

Run `la-doctor --plugin <this skill's base directory> --require-config`. Fix whatever it reports (a wrong flag, an invalid value) and
re-run until it passes.

## 7. Next steps (full run only)

Offer, each as a yes/no:
- **Type-check baseline.** If `la-typecheck` checks a language that has no baseline yet, offer
  `la-typecheck --write-baseline`. This is the one legitimate recording: afterwards the baseline only shrinks.
- **Architecture.** If `architecture: false`, offer the `la:arch-init` skill to build the model.

Never wire CI; the docs explain how when the user asks. Do not commit: the user commits the config.
