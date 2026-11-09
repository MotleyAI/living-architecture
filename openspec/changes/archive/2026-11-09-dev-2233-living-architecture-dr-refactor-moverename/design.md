## Context

See proposal.md - Why. The Python `dr-refactor` drives rope (`rope_refactor.py`): `Rename` for `rename`, `MoveGlobal`
for `move-symbol` and `MoveModule` for `move-module`, emitting rope's `ChangeSet` through `_emit`. `rope_patches.py`
already patches rope's source walker and refuses modules it cannot cover (`WalkerGap`).

Reproduced on scratch projects (current state):

| Shape | `move-module` / `move-symbol` today | `rename` today | TS twin today |
|---|---|---|---|
| `importorskip`-gated import | hoisted above the gate | unchanged | n/a |
| unsorted block | reordered on append | unchanged | unchanged |
| `from M import a, b`, one moved | split, new line at block end | name token renamed | split in place, next line |
| function-local import | left stale; module-level `import new.path` added, use dotted | renamed in place | n/a |
| `sql_pkg.client.X` | rewritten to full dotted path + new import | `sql_pkg.cli2.X` | n/a |
| `import pkg.a.mod as mod` | crash (`ModuleSyntaxError`) | alias and uses renamed | n/a |
| `import pkg.a` only for `pkg.a.f` (`move-symbol`) | removed, `import pkg.b` appended | n/a | n/a |

Cause: `MoveModule._change_occurrences_in_module` and `MoveGlobal` rename every occurrence to the fully-qualified new
name (`rename_in_module(..., imports=True)`), remove the old imports, then add `import new.path`. Every import edit
goes through `ModuleImports.get_changed_source()`, which re-writes the whole import block from scratch. Both are
whole-file rewrites. Each shape above, including the crash (the alias token is renamed to a dotted name), is an
instance of one of them.

Element principles that apply (`architecture/system.arc42.md`): 3 (language-specific code lives only in `lang` and
`refactor`), which the planner obeys by living in `python.refactor`; 2 (texts only from the shared contract), which
the new finding obeys through `findings.yaml`; 1 (twins), unaffected because Python refactors run only in the PyPI
twin, and the TS fixtures only pin the npm twin's existing output. The `refactor` spec is attached to `python.refactor`
in `architecture/model.c4`, so the requirements land there; no model or arc42 edit is needed.

## Goals / Non-Goals

**Goals:**
- One code path computes every Python move edit, so the reflow class cannot recur per shape.
- Every edit is a minimal edit at its exact position; untouched bytes are untouched by construction, not restored
  afterwards.

**Non-Goals:**
- Where `move-symbol` places the moved code in the destination: rope's position is kept.
- String references (`mock.patch("pkg.a.f")`, docs): not rewritten, as today.
- Module `rename` semantics: rope's edits are kept, including renaming a self-alias named after the module.
- General unused-import cleanup, sorting or formatting.
- A TypeScript behaviour change: the npm twin is only pinned.

## Decisions

The decisions log from planning; tags: `(user)` the user's choice, `(default)` taken as the obvious default,
`(codex)` a Codex finding folded in, `rejected (codex)` a Codex finding rejected with its reason.

1. **Rope finds, the planner edits.** Rope's occurrence finder (`occurrences.create_finder(..., imports=True)`) and
   its resolved objects (`Occurrence.get_primary_and_pyname()`) stay the only resolver. A new planner module in
   `living_architecture/refactor/` turns each occurrence into a minimal edit and applies a file's edits in one pass,
   producing a rope `ChangeSet` (`ChangeContents`, plus `MoveResource` for `move-module`), so `_emit` and the output
   format are unchanged. `move-module` and `move-symbol` both go through it. Alternatives rejected: patching rope's
   `ImportTools`/`ModuleImports` (fragile, and the block re-write stays); libcst's `RenameCommand` (a new native
   dependency, and its `AddImportsVisitor` still inserts at the top of the block). `(default)`
2. **`rename` keeps rope's `rename_in_module` edits**, which are already minimal on every shape; fixtures pin them.
   `(default)`
3. **A use whose binding breaks is rewritten**, to the new dotted path, with `import <new module>` added on the line
   after the import binding the chain's root. Alternative rejected: refusing with a located finding, which would make
   `move-symbol` refuse on the common `import pkg.a as pa; pa.f()` pattern. `(user)`
4. **A split's new statement goes on the line after the original statement ends**, at the same indentation, matching
   the TS twin. `(default)`
5. **Relative imports keep their form**, recomputed; absolute only when the target cannot be reached relatively.
   `(default)`
6. **The moved code's position in the destination is rope's.** Out of the issue's scope. `(default)`
7. **The "edit only at references" requirement is language-neutral**, and TS adapter cases pin the npm twin's
   already-minimal output. The issue's goal names "a refactor", not rope. `(default)`
8. **The SLayer acceptance diff may also hold case-3 adjacent imports**; this follows from decision 3. `(default)`
9. **Module `rename` keeps renaming a self-alias** (`import pkg.sql.client as client` → `... cli2 as cli2`, uses
   renamed). Codex asked to keep the alias. Rejected: rope renames every binding named after the module, consistently
   with `from pkg.sql import client` → `cli2`, and the uses are renamed with it, so nothing breaks. The issue's
   self-alias acceptance is for moves, where the bound name does not change. `rejected (codex)`
10. **Star-import consumers** of a symbol moved by `move-symbol`: a bare name bound through `from old import *` keeps
    its uses, and `from <new module> import <name>` is added on the line after the star import. `(codex)`
11. **"Already bound" means the same object.** An added import is skipped only when the scope's existing binding of
    that name resolves to the same object, and the same check applies to rule 3's "scope already imports it". When
    the name resolves to a different object (an assignment, a parameter, an aliased import of something else, or an
    enclosing scope), the refactor is refused with a new located finding and writes nothing. Generating an alias was
    rejected because it would rewrite the moved code. `(codex)`
12. **Classification is by resolved objects**, not syntax alone: every link of an occurrence's primary chain is
    compared by its resolved `PyName`. `X.m` survives iff `X`'s module binds `m` explicitly (by import or assignment);
    reaching a submodule only as an implicit package attribute does not count. `(codex)`
13. **Re-exports.** Import-statement re-exports (`from pkg.a import f as public_f`, package `__init__` exports) are
    rule-1 path rewrites, so they keep exporting the symbol from its new module. A `__all__` string entry naming the
    moved symbol in the source module is removed in place; star consumers are covered by decision 10. `(codex)`
14. **Import removal is exact, never cleanup.** A binding is removed only when every resolved use of it was rewritten
    by this refactor, or, in the `move-symbol` source, every use lay in the moved code. An import with another
    surviving use stays. `(codex)`
15. **Token-level import edits.** Import edits are computed on `tokenize` tokens of the statement, not on `ast` node
    spans. A removed name takes its own comma and the whitespace before it; it takes its whole physical line when it
    stands alone on that line in a parenthesized list, including that line's comment. Comments on other names stay.
    A new statement is inserted after the physical line where the statement ends (a semicolon-separated tail stays
    on its line). Covered by fixtures: a trailing comma, comments on individual names, a backslash continuation, a
    semicolon-separated statement, CRLF, a missing final newline. `(codex)`
16. **Character offsets.** `ast` columns are UTF-8 byte offsets, while rope edits use character offsets. Every
    position goes through `rope_patches.char_offset`. A non-ASCII fixture pins it. `(codex)`
17. **Relative import recomputation.** Each relative import is resolved to its absolute target in the old layout. It
    is then recomputed from the importer's new package and the target's new location, either of which may have
    moved. Imports between files that move together are unchanged. Fixtures cover a sibling's `from . import client`,
    a `from ..sql import client`, the moved module's own `from . import x`, a package move with internal relative
    imports, and a move across top-level packages, which becomes absolute. `(codex)`
18. **Permitted edit regions are defined** in the spec (reference spans, the holding import item or its statement or
    line, one adjacent inserted import, the moved code's region), so a conformance failure is decidable. `(codex)`

19. **New finding** `refactor.name-conflict: '{name} already names something else at {path}:{line}, so nothing was
    refactored'`. `(user, approved wording)`

## Risks / Trade-offs

- [Rope's finder misses an occurrence shape it never matched before, e.g. through `importlib`] → Unchanged from
  today: those were never rewritten. The type-check gate and the test suite still cover the result.
- [A use resolved by rope as "unsure"] → Moves never include unsure occurrences (unchanged); only `rename --unsure
  include` does.
- [Rope's region for the moved code depends on its trailing blank lines] → Kept as rope computes it (decision 6), and
  pinned by the existing `refactor-move-symbol-apply` golden.
- [The planner reimplements part of `MoveGlobal`'s bookkeeping (the moved code's imports, the destination's import of
  the symbol)] → Rope's own helpers (`moving_code_with_imports`, its moving region) are reused for what to move. Only
  where text lands goes through the planner.
