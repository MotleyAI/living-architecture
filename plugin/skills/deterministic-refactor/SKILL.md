---
name: deterministic-refactor
description: Use to rename or move a module/class/function/method/attribute (Python or TypeScript) and update all imports/references, with a deterministic check that nothing was missed. Mutator = dr-refactor; the guarantee = la-typecheck + dr-mock-lint + the test suite. Only sound on a compliant target (see docs/deterministic-refactoring.md).
---

**Preflight:** run `la-doctor --plugin <this skill's base directory> --require-config` once per session before using any `la-*` or `dr-*` command. If it reports the missing-config finding (the one naming `/la:init`), run the fast path of the `la:init` skill, then re-run this preflight; stop and show the user its output on anything it still reports, or on any other failure.

# Deterministic refactor

The mutator is best-effort — no tool reliably rewrites every annotated
`obj.attr`, `super()` call, and override. The **type-check gate is the
guarantee**, and it is only sound on code that meets the compliance conditions
(`docs/deterministic-refactoring.md`). If the blast radius is not typed, run `la:make-refactor-target-compliant`
first.

The file's language decides the mutator and its idioms: read
`<this skill's base directory>/../../languages/<language>.md` for each language
the refactor touches (`la-config get languages` lists the repo's).

## Procedure

1. Locate the symbol with the editor/LSP (not grep) → file, line, col.
2. **Check the verifier**: run `la-typecheck`. It runs the project's type
   checker in the project env (the one the tests use) against its committed
   baseline, and it must pass before you start. If it prints "nothing to
   check", STOP and tell the user: with no type check there is no guarantee,
   so offer to set one up (`commands.typecheck` and
   `la-typecheck --write-baseline`) first.
3. **Type the receivers** (member renames): `dr-compliance --select attr-blindspot --attr OLD <repo>`
   lists each receiver of `OLD` the checker cannot type. Type them
   (`la:make-refactor-target-compliant`) until it reports nothing; `dr-refactor`
   refuses a member rename while any remain.
4. **Dry-run** (default):
   `dr-refactor --project <repo> rename --file F --line L --col C --new-name N --docs`.
   Method renames rename the hierarchy by default. Re-run until it is the rename you want:
   - `stand-in`: a class outside the hierarchy declares `OLD`. `--with PATH:LINE` renames it too
     (a duck-typed implementation: a cache, a fake, a `cast()` target); `--without PATH:LINE` leaves it
     (an unrelated class).
   - `attr-blindspot` on a receiver that cannot be typed (a third-party `Any`): `--allow-blindspots`,
     and tell the user which.
   - a site that must keep the old name (a back-compat test or shim): `--keep PATH:LINE`, or
     `--keep PATH` for a whole file.
   Show the diff.
5. **Apply**: `--apply` is a GLOBAL flag and goes before the subcommand
   (`dr-refactor --project <repo> --apply rename ...`); trailing it errors.
6. **GATE — done only when ALL pass:**
   - `la-typecheck` passes: **no new errors** vs the baseline;
   - `dr-mock-lint <tests>` passes;
   - the full non-integration test suite (`la-config get commands.test`) passes;
   - by hand, only these: each `leftover` line the apply printed, each receiver
     `--allow-blindspots` let through, and the string-only references the language doc lists.
7. Review the diff. The user commits — never commit or `git add -A`.

## Commands

`dr-refactor` subcommands: `rename` / `move-symbol` / `move-module`. Dry-run is
default; `--apply` writes; `--project` defaults to cwd. Locator: `--line [--col]`
(1-based), `--offset N` (0-based), or `--name` (first declaration, else first
use). `rename` also takes `--with` / `--without PATH:LINE`, `--keep PATH[:LINE]`,
`--allow-blindspots` and `--docs` (comments, docstrings, strings and prose files:
qualified mentions everywhere, code-marked ones in the declaring files, the rest
listed as `leftover`). Move destinations must already exist, and a `move-symbol`
destination is a file of the same language. Run the repo's formatter afterwards.
