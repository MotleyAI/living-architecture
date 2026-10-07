## Context

See proposal.md (Why). The DEV-1990 design (archived change `2026-10-01-dev-1990-…`, D10) fixed the roadmap
this PR finishes. Today the manifest marks the three `dr-*` commands `native: [python]`, so the npm twin
forwards them wholesale. `la-typecheck` owns the only "which languages does this repo have" logic. The npm
twin already parses tsconfigs and project references (`src/lang/projects.ts`) with its bundled
`typescript@~6.0`.

Architecture that binds this change (`architecture/system.arc42.md`):
- P1 twins: routing, merging, `la-config` language keys and `la-doctor` are neutral, so both twins implement
  them identically and conformance pins them.
- P2: every new text goes to `findings.yaml`; check sets and file-eligibility facts go to `languages.yaml`.
- P3: TS refactor code lives only in `typescript.refactor`, which reuses `typescript.lang` for tsconfig and
  project loading.
- P4: the bundled TypeScript only; target files are read, never executed or imported.

## Goals / Non-Goals

**Goals:**
- A TS repo gets verified refactoring and a Python-free toolchain end to end.
- Every Python repo's observable output stays byte-identical.
- Skills carry no language idiom; one per-language document holds them.

**Non-Goals:**
- A facts protocol for `dr-*` (see D2).
- Rolling back a refactor whose writes fail half-way (see D5).
- Node version policy in `la-doctor`.
- Treating a non-root tsconfig as a language marker: such a repo sets `commands.typecheck.typescript`
  explicitly, which already makes TypeScript a repo language.

## Decisions

### D1 — One definition of repo languages, in `config`
Repo languages = languages with an explicit `commands.typecheck` command, plus languages with a root marker
and a non-exempt, non-ignored file. `la-typecheck` applicability is that set minus `null` entries, which
preserves today's behaviour exactly. The logic moves from `typecheck` into `config`, which `typecheck`,
`doctor`, `refactor` and `la-config` already import.
Alternative: reuse typecheck applicability as is. Rejected: `null` (typecheck off) would also drop the
language from skills, doctor and `dr-*` expansion.

### D2 — `dr-*` routing merges captured output, not facts
Each language's block is rendered by its own twin, so concatenating the blocks in registry order is
identical whichever twin orchestrates. The other twin runs first with stdout captured; nothing prints until
it succeeded (exit 0 or 1). A facts protocol earns its keep only where a report is computed across languages
(the conventions text ratio); `dr-*` lines are per file.
Alternative: a schema-checked facts document. Rejected: a second rendering path for texts each twin already
renders.

### D3 — `dr-*` native to both twins; the manifest lists `native: [python, typescript]`
The routing lives in each twin's `refactor` node (`refactor → config` for repo languages, `refactor → twin`
for the hand-off). `dr-refactor` with an other-language source forwards wholesale; cwd and raw args are
preserved so relative paths resolve the same.

### D4 — One LanguageService per project
Solutions with project references can differ in `paths`, `moduleResolution`, JSX and strictness, so a single
service over the union of files would resolve some imports wrongly. Each project in the reference graph
gets its own service with its own options; the owning project is the first in preorder that contains the
file. Rename runs in every project that contains or references the owner; identical edits are merged, and
conflicting ones fail.
Alternative: one service over the union. Rejected for the reason above.

### D5 — Compute and validate, then write
The full change set (text edits plus moves) is computed and validated before any write: overlapping edits,
a move onto an existing path, a missing destination. Writes then happen in path order, and moves last. There
is no rollback after a mid-write I/O failure, which matches rope's `project.do`.

### D6 — Move to file
`move-symbol` asks `getApplicableRefactors` at the declaration name with `interactiveRefactorArguments` and
takes the refactor and action named "Move to file". If none applies, the finding is `not-movable`. The
action's file edits are taken as is (imports included). `move-module` uses `getEditsForFileRename` for a file
or every file under a directory, then moves on disk.
Re-exports are ours: every named or default re-export of the moved symbol is rewritten to the new file (a
re-export that also lists symbols that stay is split), and a barrel that reached the symbol through
`export * from` the old file gets an explicit `export { <name> } from` the new file, unless it already has
`export * from` the new file.

### D7 — Stable texts only
Headers mirror rope's (`Renaming <a> to <b>:`, `Moving global <a>:`, `Moving module <a>:`) and come from
`findings.yaml`, as do every error. TypeScript's own messages (`localizedErrorMessage`, diagnostics) are
never printed; each failure maps to a finding id.

### D8 — Diff format pinned by vectors
`shared/vectors/diff.yaml` holds (old, new, path) → expected text. The Python suite checks it against
difflib's `unified_diff`, which is what rope prints, and the Node suite checks its own formatter, written
against the vectors.

### D9 — Checker-based TS checks
`untyped-def` comes from the checker's implicit-any diagnostics (parameter, binding element, rest) with
`noImplicitAny` forced on, so contextual typing, JSDoc and inference count. `--attr NAME` uses the receiver's
checker type. The `tsconfig` check reads the effective options after `extends`, treating `noImplicitAny` as a
strict-family flag. Mock receivers resolve through the checker: an import from `vitest` or `@jest/globals`,
or the unshadowed global.

### D10 — `--select` has no manifest default
Absent means every check of each file's language (from `languages.yaml` `compliance_checks`). An explicit
`''` keeps today's Python behaviour (nothing selected, exit 0).

### D11 — Init is `la:arch-init`
`la:arch-init` already wires `la-typecheck --write-baseline` and builds the as-is model with `la-arch-scaffold` in
both twins; this change only removes its language idioms.

### D12 — Skill facts and idioms
Skills name `la-config get languages` and `la-config get lang.<language>.<key>`, and read
`<skill base dir>/../../languages/<language>.md`. The language-only token list lives once in
`shared/vectors/skill-leaks.yaml` and is read by `python/tests/test_skills.py` and
`node/test/skills.test.ts`. `npx` and `npm` are allowed because the OpenSpec and LikeC4 CLIs need them in
every repo.

### D13 — Model change
- New node `typescript.refactor` (`src/refactor`) with arrows `cli → refactor`, `refactor → contract`,
  `refactor → lang`, `refactor → config` and `refactor → twin`.
- New arrows `python.refactor → config` and `python.refactor → twin`.
- Diagrams regenerate.
- The new `refactor` spec attaches to `python.refactor` at archive time.

Each `architecture/` edit needs the user's per-edit OK.

## Risks / Trade-offs

- [The TypeScript move-to-file refactor changes between minor releases] → TypeScript is pinned `~6.0`;
  conformance pins its edits; a TypeScript bump is a reviewed golden change.
- [Per-project services cost memory on large solutions] → Services are created lazily, only for projects
  that contain or reference the owner.
- [The leak list misses a token] → The list is shared and extended whenever review finds a leak; the
  config-key test catches stale keys.
- [The worktree-term acceptance depends on DEV-1989 progress] → It is the last task of pr-review; the PR
  merges only after it passes.

## Migration Plan

Version 0.3.0 for both packages, the plugin and every `--expect` pin; `node/package.json` becomes public.
Users run `uv tool install living-architecture==0.3.0` or `npm install -g living-architecture@0.3.0`. Python
repos see no output change. Rollback is reverting the PR before the tag; after publish, a 0.3.1 fix.
