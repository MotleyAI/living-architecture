## Context

See proposal.md (Why). DEV-2301 and DEV-2310 are merged to main and archived; this branch has merged `origin/main`.
Today (`python/src/living_architecture/refactor`):

- `rope_refactor.move_symbol` / `move_module` build a rope `Project` (`_RopeProject`), map paths to rope resources
  (`resource`, `_destination`), locate the moved symbol with `create_move` (offset converted by `_rope_offset`), run
  the `checks` phase (`walker_gaps`, `baseline_probe`), call `move_edits.symbol_move_changes` /
  `module_move_changes`, and print rope's `ChangeSet` through `rename_map.source_bytes`, `change_set_writes` and
  `emit` (header = rope's `str(ChangeSet)`: `Moving global <f>:` / `Moving module <m>:`).
- `move_edits.py` writes every edit itself over rope's newline-normalised text, with its own scope model (`_Scopes`,
  `_Scope`, `_Binding`). rope supplies the references (`occurrences.create_finder`, the occurrence's primary via
  `_module_object` / `_primary`), the moved region (`MoveGlobal._get_moving_region`), the moved code with its imports
  (`_get_moving_element_with_imports`, read through `FromImport` / `ImportInfo` in `_needed_import`) and module names
  (`libutils.modname`, `_package`). `_explicitly_binds` vetoes rewriting `pkg.sub` when the package binds `sub`.
- `module_rename.py` (DEV-2310) already runs on la's project model: `Snapshot`, `TextEdit`, `FileMove`,
  `changes_of`, `emit`, `diff_render.move_description` (whose `rename from/to` text is hard-coded).
- `static_resolver.Resolver` resolves names, imports, star imports with literal `__all__`, and module attribute chains
  over first-party modules found by `patch_targets.SourceFolders`; a module is found only when it is exactly one file,
  so namespace packages resolve to nothing.

Probed on scratch projects before planning (all on today's code):
- `--line` on a method or a module name in an import crashes with an `AttributeError` traceback (rope returns
  `MoveMethod` / `MoveModule`, cast to `MoveGlobal`); on a local, rope's `RefactoringError` traceback escapes.
- `--symbol` on an import binding, and `--line` on a reference, move the declaration out of its own module.
- An `@overload` group: only the implementation moves; the stubs stay. A twice-assigned name: the first assignment
  moves and the source gets `from <dest> import X` while `X = 2` still rebinds it.
- Guarded imports: imports inside `if TYPE_CHECKING:` and `try:` used only by the moved code are removed from the
  source, leaving empty blocks (a syntax error); the destination gets `from <source> import T, json` (`T` exists only
  for type checkers); `from __future__ import annotations` is dropped; a function-local `from .x import y` in the moved
  code is left pointing at the destination's package.
- Namespace packages: `move-module` of a namespace directory crashes (rope: "Cannot move non-package folder");
  `move-module` out of one leaves `from pkg.ns import m`; a module rename through one leaves `pkg.ns.m.Y`.

Principles that apply (`architecture/system.arc42.md`; `python.refactor` has no arc42 of its own):
1. Twins — the behaviour is Python-only; new cases are Python `adapter` cases. The renamed message keys keep every
   TypeScript golden identical. The locator refusal matches the npm twin's (`refactor-ts-not-movable-imported-use`).
2. Parameters and texts only from the shared contract — the move headers and moved-file text move from rope and a
   hard-coded string into `shared/findings.yaml`; `refactor.guarded-import` is added there.
3. Language-specific code only in `lang` and `refactor` — everything is in `refactor`.
4. No target-repo code runs — the static resolver reads files only.

Spec attachment: `refactor`, owned by `python.refactor`. No model or arc42 edit: no new import edge
(`refactor -> contract` exists).

Symptom and structural cause: the move planner answers each question twice — rope for what an occurrence is,
`_Scopes` for which binding it is and whether a name is free — and those must agree by hand; contract texts come from
rope; locating trusts a cast. The fix: one project model (la's), one resolver for scoping and imports (the static
resolver, whose scopes the planner also edits by), the AST for declarations and regions, and every text from
`shared/`.

## Goals / Non-Goals

**Goals:**
- No rope object or call on the `move-symbol` / `move-module` path, except the `checks` phase's walker-gap check.
- Byte-identical stdout, stderr, exit code and written bytes on every existing Python `move-symbol` and `move-module`
  golden.
- No traceback for any locator; no move that leaves the source or destination unparsable or an import unbound.

**Non-Goals:**
- Removing rope, `rope_patches.py`, the walker-gap findings, the `rope-walk` compliance check and their docs:
  DEV-2312.
- The TypeScript twin's behaviour (only its two message-key call sites change).
- A version bump: versions move at release (AGENTS.md); approved scope cut of Codex finding 11.
- Moving a guarded (`try` / other `if`) import's dependency automatically: refused with `refactor.guarded-import`.

## Decisions

1. **References from the static resolver; moves start no language server.** Rejected: the occurrence index (about
   one full type check per move; it has no module-reference kind). *(user, issue 2026-11-16)*
2. **An import-order difference the differential cannot reproduce is raised with the user** (fallback idea: source
   order plus the repo's formatter). *(user, issue 2026-11-16)*
3. **The walker-gap check stays in a move's `checks` phase** with today's candidate rule; DEV-2312 removes it.
   *(default: DEV-2312's scope)*
4. **One scope model.** The planner runs on `static_resolver.Module` / `Binder`; `Binder` also records, for each
   import binding, its statement and item index (and whether it sits in the module body or a block). `_Scopes`,
   `_Scope`, `_Binding` are deleted; name-conflict checks, "binds module", import drops and use lookups read the
   resolver's scopes. Rejected: keeping `_Scopes` for edits (two scope models that can drift). *(user)*
5. **Approved scope extensions.** *(user)*
   - Locating without rope, by AST: a site on a top-level declaration of `--file`; every non-movable site (method,
     local, parameter, module name, multi-name or same-line assignment, block-bound name, repeated top-level binding,
     import binding, reference) refuses with `refactor.not-movable` instead of a traceback.
   - Moves on la's project model: `Snapshot`, `TextEdit`, `FileMove`, `changes_of` / `emit` as module renames use;
     files from `language_files`, module names from `ProjectLayout`. Deleted: `_RopeProject`, `resource`,
     `_destination`, `_rope_offset`, `source_bytes`, `change_set_writes`, every rope import in `move_edits.py`.
     `outside-project`, `destination-missing`, `source-missing` keep their texts.
   - Move texts from `shared/` under neutral keys: `refactor.ts-move-symbol-header` → `refactor.move-symbol-header`,
     `refactor.ts-move-module-header` → `refactor.move-module-header`, `refactor.ts-moved` → `refactor.moved`;
     `scripts/sync-shared`; both twins' call sites and `diff_render.move_description` use them. Texts unchanged.
6. **Docs wording.** *(user, approved wording)*
   - `plugin/languages/python.md:16`: "`dr-refactor` resolves a rename's occurrences with the basedpyright bundled
     with la and computes every rename and move itself."
   - `docs/deterministic-refactoring.md:12-13`: "Python resolves a rename's occurrences with the bundled basedpyright
     and computes every rename and move itself;"
   - `docs/how-it-works.md:96`: "(la with the bundled basedpyright for Python, the TypeScript language service for
     TypeScript)"
   - `docs/living-architecture-in-questions-and-answers.md:23`: "(Python with the bundled basedpyright and la's own
     resolver,"
   - `docs/refactoring-internals.md` table, rope row: "rope (+ la's walker patches) | The walker-gap check: a move's
     `checks` phase and `dr-compliance --select rope-walk`. | Only that check is left; no refactor is computed with
     rope."; static resolver row "Used for" ends: "…entry locations, the names basedpyright leaves unresolved,
     retarget's lookups, module renames and moves."; stdlib row "Used for" starts: "Edit placement, a moved symbol's
     region and imports, `--docs` mentions, …"; diagram: `cmd --> rope` becomes `cmd -- "walker-gap check" --> rope`.
7. **A repeated top-level binding**: an `@overload` group (the contiguous run of `@overload`-decorated defs of the
   name plus the non-overload def directly after them) moves as one region; any other repeated binding refuses with
   `refactor.not-movable`. Rejected: refusing overload groups too (overloaded functions unmovable). *(user)*
8. **Namespace packages are in scope**: the resolver models a source-folder directory without `__init__.py` as a
   module with no bindings whose submodules resolve as attributes; `move-module` moves one like a package; module
   renames rewrite chains through one. Rejected: a new refusal finding; leaving it xfailed against a new issue. Their
   cases are `golden: manual`, deliberate behaviour, not evidence of rope equivalence. *(user)*
9. **New fixtures are Python `adapter` conformance cases.** Where today's output is valid, its golden is written by
   today's rope path (`LA_UPDATE_GOLDENS=1`, reason "new case") before the switch; where today's output crashes or
   breaks code, the golden is hand-written (`golden: manual`) to the new rules. *(default)*
10. **Tests aligned with the plan**: `python/tests/test_contract.py:625-626` pins the old key names → renamed;
    `python/tests/test_move_edits.py` calls `module_move_changes` / `symbol_move_changes` with rope objects → moved
    to the new entry points, same cases and expectations. *(user, with the plan's approval)*
11. **Source side: only imports directly in the module body are removed** when every use of their names lay in the
    moved code; an import inside a block stays, possibly unused. Rejected: removing it and an emptied block (edits
    guard structure, e.g. a `try`'s `except` body). *(user)*
12. **Destination side for a guarded import**: a name bound in the source only under `if TYPE_CHECKING:` gets its
    import, made absolute, inside the destination's top-level `if TYPE_CHECKING:` block (after its last statement),
    else in a new block after the leading import block, with `from typing import TYPE_CHECKING` added when unbound;
    the usual already-bound and conflict rules apply. A name bound only under any other guard (`try` / `except`,
    another `if`, a loop) exits 1 with the new finding `refactor.guarded-import`, wording: "{path}:{line}: the moved
    code reads a name this guarded import binds; move it by hand". Rejected: hoisting every guarded import unguarded
    (type-only imports become runtime, fallbacks dropped); refusing every guarded import (blocks `TYPE_CHECKING`).
    *(user, approved wording)*
13. **`from __future__` imports** of the source that the destination lacks are added as the destination's first
    statement after its docstring. Rejected: refusing (blocks most typed modules); adding only when "needed"
    (heuristic over annotations). *(user)*
14. **Relative imports inside the moved code** are recomputed for the destination like rule 1 recomputes a moved
    module's own relative imports (relative when reachable, else absolute); absolute ones stay. Rejected: making every
    one absolute (inconsistent with `move-module`). *(user)*
15. **Newlines** (Codex 1): every inserted line and the moved text take the target file's line break; the moved text
    is converted from the source's. `Snapshot.encode` keeps BOM and encoding but does not translate newlines, so the
    planner works on the raw text and writes the file's own break. *(codex)*
16. **Package attributes** (Codex 4): rule 2 holds — the use stays — when the package's `__init__` binds the name
    explicitly anywhere in its module scope (blocks included) or defines a module-level `__getattr__`. A use is
    rewritten only when the resolver shows the name reaches the moved module solely as a submodule attribute.
    *(codex)*
17. **The source is always `--file`** (Codex 5, amended by the user's Q11): it drives the walker-gap names, the
    baseline probe, the region, the source edits and `moved_code=True` alignment. Rejected: following an import
    binding or a reference into its declaring file, as rope did (the twins would differ, and `refactor.not-movable`'s
    "a top-level declaration of {path}" would not fit). *(user)*
18. **Walker-gap candidate set unchanged** (Codex 6): rejected — after this change nothing walks with rope during
    the move, so no gap can surface later; DEV-2312 removes the check. *(rejected (codex))*
19. **Region algorithm** (Codex 7), on the source's lines: start = line of the first decorator (else the
    declaration's first line; for an overload group, of the group's first member); while the line above starts with
    `#` in column 0, start moves up one. End = the declaration's (group's) last line by AST `end_lineno`; while the
    next line holds only whitespace (form feeds included), end moves down one. A variable's region is its logical
    line (all physical lines of the statement). The moved text is the region's text with trailing whitespace stripped
    plus one line break. The differential compares raw spans and new text. *(codex)*
20. **Namespace package identity** (Codex 8): a dotted path is a namespace package when one or more directory
    portions of it exist under `ProjectLayout`'s source folders, none holds `__init__.py`, and no regular module or
    package of that name exists; a submodule found in more than one portion is unresolved; `move-module` of a
    namespace directory moves that one directory. *(codex)*
21. **Stale-file detection** (Codex 9): every write's old bytes come from the `Snapshot` read before planning and
    `writer.verify` checks them before mutating, as module renames do. *(codex)*
22. **Namespace scope vs byte-identity** (Codex 10): rejected — the user put namespace packages in scope (decision
    8); their cases are manual goldens. *(rejected (codex))*
23. **Contract key renames** (Codex 11): `scripts/sync-shared`, the npm call sites, the npm tests and
    `scripts/conformance-cross` over the touched TypeScript cases are part of the change. The version bump is
    rejected: AGENTS.md moves versions at release, and this PR changes tool inputs anyway. *(codex; bump: rejected
    (codex))*
24. **Conformance hygiene** (Codex 12): every new case is listed in `conformance/INVENTORY.md`; rope-written goldens
    are reviewed and their reason stated in the commit message; the differential compares raw edits (span and new
    text), rendered stdout and stderr, and findings, not only normalised sets. *(codex)*
25. **Destination import computation** (from the issue's reduction, plus decisions 12–14): for each name the moved
    code reads (`ast.Name` loads, annotations included): a name a top-level import of the source binds → that import,
    made absolute; a name the source defines (def, class, assignment at module level) → `from <source module> import
    <name>`; a name bound only by a guarded import → decision 12. Each import keeps only the names the moved code
    reads and the destination does not already bind to the same object. Order: `__future__` (decision 13, placed
    first), standard library (`sys.stdlib_module_names`), third-party, project (resolvable under the source folders);
    within each, plain `import` before `from`, then by text. *(default, from the issue)*

## Risks / Trade-offs

- [The static resolver becomes load-bearing for move edits] → its scope is narrow (bare names, module attribute
  chains, first-party imports); the differential over every move case, `test_move_edits.py` and the new fixtures
  must show no unexplained difference before the old path is deleted.
- [Import order or grouping differs from rope's on an input the corpus lacks] → fixtures first for the thin areas;
  any difference stops the work for the user (decision 2).
- [Rebuilding the planner on `Binder` changes a name-conflict outcome] → the four name-conflict cases and the unit
  conflict tests pin today's results; a difference stops for the user.
- [Moves that rope "succeeded" on now refuse (locators, repeated bindings, guarded imports)] → each refusal names the
  file and line; rope's output on those inputs was broken or undocumented.
- [CRLF / BOM handling moves from rope to la] → decision 15 plus mixed-newline cases with `--apply`.

## Migration Plan

Build the new path beside the old (`move_edits` on the resolver, rope's path untouched), run the differential, stop
and ask on any difference not pinned by a manual golden, then switch `rope_refactor` to the new path and delete the
old one. No rollback beyond git; rope stays installed until DEV-2312.
