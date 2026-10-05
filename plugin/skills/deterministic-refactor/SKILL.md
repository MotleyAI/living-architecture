---
name: deterministic-refactor
description: Use to rename or move a Python module/class/function/method/attribute and update all imports/references, with a deterministic check that nothing was missed. Mutator = rope (dr-refactor); the guarantee = the project's type checker + dr-mock-lint. Only sound on a compliant target (see docs/deterministic-refactoring.md).
---

**Preflight:** run `la-doctor --expect 0.2.1 --require-config` once per session before using any `la-*` or `dr-*` command. If it reports the missing-config finding (the one naming `/la:init`), run the fast path of the `la:init` skill, then re-run this preflight; stop and show the user its output on anything it still reports, or on any other failure.

# Deterministic refactor

The mutator is best-effort — no tool reliably rewrites every annotated
`obj.attr`, `super()` call, and override. The **type-check gate is the
guarantee**, and it is only sound on code that meets the compliance conditions
(`docs/deterministic-refactoring.md`). If the blast radius is not typed, run `la:make-refactor-target-compliant`
first.

## Procedure

1. Locate the symbol with the editor/LSP (not grep) → file, line, col.
2. **Check the verifier**: run `la-typecheck`. It runs the project's type
   checker against the PROJECT env (the same interpreter the tests use) and its
   committed baseline, and it must pass before you start. If it prints "nothing
   to check", STOP and tell the user: with no type check there is no
   guarantee, so offer to set one up (`commands.typecheck` and
   `la-typecheck --write-baseline`) first.
3. **Dry-run** (default):
   `dr-refactor --project <repo> rename --file F --line L --col C --new-name N`.
   Show the diff. Method renames rename the hierarchy by default.
4. **Apply**: `--apply` is a GLOBAL flag and goes before the subcommand
   (`dr-refactor --project <repo> --apply rename ...`); trailing it errors.
5. **GATE — done only when ALL pass:**
   - `la-typecheck` passes: **no new errors** vs the baseline (a missed
     annotated usage, `super()` call, or orphaned `@override` surfaces here).
     Known rope misses the gate catches: receivers narrowed by `isinstance`
     rather than annotation (e.g. `other.attr` inside `__eq__`), and
     constructor keyword arguments of dataclass/Pydantic fields
     (`Cls(attr=...)`);
   - `dr-mock-lint <tests>` passes;
   - the full non-integration test suite passes;
   - grep the string-only refs no static tool sees: `importlib`, `getattr(`,
     `__all__`, `patch("dotted.path")`, entry points, config paths, and — for
     a Pydantic field rename — `model_copy(update={"NAME": ...})` /
     `model_dump` consumers keyed on the old name.
6. Review the diff. The user commits — never commit or `git add -A`.

## Commands

`dr-refactor` subcommands: `rename` / `move-symbol` / `move-module`. Dry-run is
default; `--apply` writes; `--project` defaults to cwd; `--no-in-hierarchy`
disables hierarchy rename. Locator: `--line [--col]`, `--offset N`, or `--name`.
Move destinations must already exist. For refactors that hinge on third-party
types, run `dr-refactor` under the project's venv Python. Run a formatter
(ruff/black) afterwards — rope reflows imports.
