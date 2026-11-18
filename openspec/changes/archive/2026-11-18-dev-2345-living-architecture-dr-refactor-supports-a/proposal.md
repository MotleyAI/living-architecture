## Why

A vocabulary rename (one word replaced by another across a repo) needs thousands of rename-map entries and hundreds
of site decisions, and `dr-refactor` only takes the finished map. In the SLayer vocabulary rename this cost about
half a day of throwaway scripts for the map, a hand-built 472-entry locals map and about 150 hand-classified
stand-ins (DEV-2345; DEV-2340 items 1, 2, 6, 14 and 25).

## What Changes

- A word table (`words`, `carve_outs`, `entries`), validated against a new shared schema, describes a vocabulary
  rename: which word becomes which, and where a word keeps its old sense.
- `dr-refactor generate-map TABLE` writes the rename map for a word table: one entry per declaration, and per
  module, whose name holds a word. It leaves out and lists what a carve-out matches, and carries the table's
  hand-written `entries` through every regeneration.
- A symbol path may be a wildcard, `*.<locals>.NAME` or `Scope.*.<locals>.NAME`: one entry renames every local of
  that name in the file or scope.
- Stand-ins are left by default when they are pytest fixtures, or, with `--words TABLE`, when a carve-out matches
  them.
- With `--docs --words TABLE`, a code-marked mention a carve-out covers is listed, not rewritten.
- A Python rename located on the `as` name of a module import renames the alias only. Today it moves the module and
  leaves the import path, which breaks the import.
- Declined: a per-site new name (`--with PATH:LINE=NAME`), since a stand-in gets its own name as a map entry; a
  phrase matcher for prose. Deferred: the re-check after a map change (DEV-2340 item 8), to be designed after
  DEV-2323.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `refactor`: new requirements for word tables, map generation, wildcard local paths, stand-ins left by default
  and carved `--docs` mentions; the routing, locator, stand-in, `--docs`, symbol-path and rename-map requirements
  change to admit them.

## Impact

- `shared/`: `cli.yaml` (`generate-map`, `--words`, the `--symbol` help), `schema/word-table.schema.json`,
  `findings.yaml` (six findings), `languages.yaml` (fixture decorators), a new vector file for word replacement.
- Both twins' `refactor` packages and their vendored `shared/` snapshots.
- `conformance/` cases and `conformance/INVENTORY.md`.
- `docs/deterministic-refactoring.md`, `docs/commands.md`, `plugin/skills/deterministic-refactor/SKILL.md`.
- No new architecture element or import arrow; the `refactor` spec stays owned by `python.refactor`.
