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
- Checking the module finder against Python's import machinery, an import-and-compare test harness, the resolver
  comparison for module renames, and the comparison's known gaps (decision 38): DEV-2350.

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

### Output checks (second pass on the open PR; tasks sections 8–13)

Symptom: three review rounds each found narrower cases where a move wrote a file that does not parse, cannot be
encoded, or whose names resolve differently (about 20 point fixes). Structural cause: the planner writes each file's
text from per-case edit rules and nothing checks the result before `emit` prints and writes it, so every case no rule
covers is silently wrong output. Fix: check the result itself, once, on the one path every Python refactor writes
through. A case no rule covers then refuses instead of writing.

26. **Two checks, in this order, before anything is printed or written.** (1) *Validity*, for every Python refactor
    (rename, rename-map, retarget, moves). (2) *Resolver comparison*, for `move-symbol` and `move-module` only. Options
    weighed for (1): moves only, or every refactor through one function; taken: every refactor, one code path
    (probed: `rename --new-name valué` in a `# coding: ascii` file prints a `UnicodeEncodeError` traceback today).
    *(user: scope "validity check and resolver comparison"; default: one path)*
27. **Validity lives in one function**, new module `refactor/output_check.py`:
    `checked_write(snapshot: Snapshot, rel: str, text: str) -> FileWrite`. It replaces `rope_refactor._encoded` and the
    inline `FileWrite(... snapshot.encode(rel, text))` of `rename_map.changes_of`; those two call sites are the only
    places a Python file's new text becomes bytes. Steps: (a) `snapshot.encode(rel, text)`; on `UnicodeEncodeError`
    raise `RefactorError(message("refactor.unencodable", path=rel, encoding=snapshot.encoding(rel)))`. (b) Decode the
    new bytes as a fresh read would: strip a UTF-8 byte order mark, take `read_str_coding(body) or "utf-8"`, decode;
    when that raises `UnicodeDecodeError` or `LookupError`, or the result is not `text`, raise `refactor.unencodable`
    with that declared encoding. (c) Only when `contract.language_of(rel) == "python"` and
    `snapshot.source(rel).tree is not None`: `SourceFile(Path(rel), text).tree` must not be None, else raise
    `RefactorError(message("refactor.unparsable", path=rel))`. `rel` is the path the file was read at. No new finding:
    both texts already say exactly this. A created file has no snapshot entry, so the same module also has
    `checked_create(rel: str, text: str) -> FileWrite` (`old=None`, UTF-8 bytes, step (c) whenever `rel` is a Python
    file); `ModuleRename.stub` (`module_rename.py`), the one place that builds a created Python file, returns its
    result (the stub template comes from the user's `living-architecture.yaml`, so it can fail to parse). The
    type-check baseline that `emit` realigns (`baseline_align.py`) is the checker's JSON, not a Python file: it is
    outside both checks. *(default; stubs and baseline: codex)*
28. **New finding for the comparison** *(user, approved wording)*:
    `refactor.resolution-changed: '{path}:{line}: {name} would not resolve as it does now, so nothing was refactored; move it by hand'`
29. **Spec requirement "Python refactors check their output before writing"** *(user, approved wording)*: the three
    paragraphs of that requirement in the spec delta, verbatim. Its scenarios are the acceptance criteria.
30. **The project after the move is built on disk, in a temporary directory, by the real writer.** New module
    `refactor/move_verify.py`. Options weighed: an in-memory overlay of the file system under `SourceFolders`,
    `ProjectLayout` and `MoveProject.dotted` (all read the disk directly: `is_file`, `is_dir`, `rglob`, `os.listdir`),
    or a copy. Taken: the copy, because it checks the bytes and layout that `--apply` will produce, with the writer's own order
    of writes and moves, and needs no second file-system model. (The copy is no git repository, so `writer._move`
    takes its `os.replace` branch there, not `git mv`; both leave the same files.) Steps: `tempfile.TemporaryDirectory(prefix="la-verify-")`;
    create every directory and copy every `.py` file `ProjectLayout` sees (add a public
    `ProjectLayout.resources() -> Iterator[tuple[str, bool]]` over `_children`, recursive: non-ignored, non-symlink;
    the bool is "is a directory"); also every `rel` of `project.files()` the layout skipped: when it is a symlink whose target resolves inside the
    project, a symlink to the same target inside the copy (module identity goes by resolved path,
    `SourceFolders.files`); otherwise a regular file written from `snapshot.data(rel)`; and copy the root
    `pyproject.toml` when it exists; then
    `writer.apply(tmp_root, writes, moves)` with the move's own writes and moves (not the baseline write, not
    `unchanged`); then `after = MoveProject(tmp_root)`. The directory is removed when the check ends, also on a
    refusal. Nothing under the project root is created. *(default)*
31. **What is compared: a fingerprint per file**, built only from `Resolver.resolve`, `Resolver.values`,
    `Resolver.module_values`, `Resolver.declaration` and each `Module`'s `Binder`. For `before = project` and `after`,
    and every `rel` of `before.files()` whose `before.module(rel)` is not None, the file's fingerprint is two tables.
    `final(rel)` is `rel` after the move's `FileMove`s (`rel == m.rel` → `m.dest`; `rel` under `m.rel + "/"` → the
    same suffix under `m.dest`; confirm `dest` is the full new path where `ModuleMove.move` is built).
    - **Reads** (`Counter` of keys, each key also remembering its `(line, col, text)` occurrences). The reads are the
      `ast.Name` loads and `ast.Attribute` loads of `binder.loads` plus the names and attributes inside
      `binder.annotations` (as `move_edits.File._loads` collects them), reduced to *maximal chains*: drop every node
      that is the `.value` of a collected `ast.Attribute`, and drop a chain whose innermost receiver is not an
      `ast.Name`. For a chain with root name `r` read in scope `s`:
      - *value*: the canonical value (decision 32) of `resolve(module, s, p)` for the longest prefix `p` of the chain
        where it is not None; if none, `("unbound", r.id)` when `values(module, s, r)` is empty, else
        `("opaque", r.id)`;
      - *tail*: the attribute names after `p` (after `r` when there is no `p`), joined with `.`;
      - *order*: `"annotation"` for a read that came from `binder.annotations`; else `"deferred"` when `s` or a scope
        around it has kind `function`; else `"local"` when `s.resolving(r.id)` is not the module scope; else `"bound"`
        when the module scope has a binding of `r.id` positioned before the read (an entry of `binder.bound` whose
        `scope.owner(name)` is the module scope, whose own scope is not inside a function, and whose node's
        `(lineno, col_offset)` is smaller; a `binder.star_nodes` import positioned before the read counts as a binding
        of every name), else `"not-yet"`.
      A read whose value is `("typing", "TYPE_CHECKING")` is left out of the table (a move may add an
      `if TYPE_CHECKING:` block).
    - **Top-level names**: for each name of `module.scope.bindings`, the canonical value of
      `combine(module_values(module, name))`.
    - **Exports**: `module.all_names` (the strings of a literal `__all__`, None without one).
    *(default; exports: codex)*
32. **Canonical values**, so that a value compares equal before and after although lines and module names shift:
    - `None` → `"?"`; `("typing", n)` unchanged;
    - `("module", dotted)`: when `project.folders(dotted)` finds a path, `("module", <that path relative to the
      project root>)`, mapped through `final` on the before side; else `("module", dotted)` as written;
    - `("decl", …)`: with `(module, node) = resolver.declaration(value)` and `key` its `node_key`: when
      `binder.enclosing[key]` is the module scope (or an `annotation` scope directly under it), `("decl", <file>,
      <name>, <ordinal>)`, where `<file>` is the module's path relative to its project root (`final` applied on the
      before side), `<name>` is `node.name` or `node.id`, and `<ordinal>` is the declaration's index among the
      module-level declarations of that name in the file, ordered by line then column; any other declaration →
      `("local", <name>)`. `declaration` returning None → `("opaque", <the value's string>)`.
    - *the moved declaration* (`move-symbol` only): before, a module-level declaration of the source file whose key is
      in `MovedSymbol.keys`; after, a module-level declaration of the destination file named `MovedSymbol.name`; both
      → `("decl", <destination file>, <name>, "moved")`.
    *(default)*
33. **The comparison.** With `F0`, `F1` the fingerprints before and after:
    - `move-module`: for every file, `F1[final(rel)]` reads must equal `F0[rel]` reads.
    - `move-symbol`: let `M` be the reads of the source file whose root name starts inside `MovedSymbol.region`.
      Expected reads: source `F0[source] − M`, destination `F0[dest] + M`, every other file `F0[rel]`.
    - both: for every file, every top-level name present in both `F0[rel]` and `F1[final(rel)]` must have the same
      canonical value. A name present on one side only is no difference (a dropped import that something still needs
      shows up as a changed read or a changed top-level name elsewhere, since every file is compared).
    - both: for every file the exports must be equal, except that `move-symbol` expects the source's exports
      without `MovedSymbol.name` (the planner removes that entry; the spec adds none to the destination).
    - a file that parsed before and has no module after is `refactor.unparsable` naming it (cannot happen after
      decision 27, kept as the guard).
    The first difference, files in `final(rel)` order: among read keys counted more often after than expected, the
    occurrence with the smallest `(line, col)` in the new text → `refactor.resolution-changed` with `final(rel)`, that
    line and the chain as written (`ast.unparse`); when there is none, among keys counted less often, the occurrence
    with the smallest `(line, col)` in the old text, with `rel` and that line; when the reads agree, the first
    differing top-level name in name order, with `final(rel)`, the line of its first binding in the new text and the
    name; when those agree too, differing exports, with `final(rel)`, the line of the last top-level `__all__`
    assignment in the new text and the name `__all__`. One finding line only. *(default)*
34. **Annotations are never "reads that run while the module is imported"** (part (b) of the requirement): a forward
    reference in an annotation is legal under `from __future__ import annotations` and under Python 3.14's deferred
    evaluation, and a moved function's `x: Later` gets `Later` imported at the destination's top, which would differ
    from "not yet bound" in the source. Annotation reads still take part in (a). *(default; a simplification the user
    has been told about)*
35. **Where the checks run.** `rope_refactor._emit` builds its writes with `checked_write`, then, when the move has
    writes or moves, calls `move_verify.verify(project: MoveProject, symbol: tuple[MovedSymbol, str, str] | None,
    writes: list[FileWrite], moves: list[FileMove]) -> None` (`symbol` is the moved declaration with its source and
    destination files for `move-symbol`, None for `move-module`; `final` is derived from `moves` alone), then calls
    `emit`. Both run with and without `--apply`. A refusal raises `RefactorError`,
    which `run_refactor` already prints with exit 1; stdout stays empty. No new progress phase and no new timing phase
    (either would change every move golden and `shared/`); the work is charged to `references` by wrapping it in
    `timed("references")`. *(default)*
36. **Every existing golden but one stays byte-identical.** The one: `refactor-move-symbol-qualified-self-reference-declaration`
    moves `def f(n, step=lambda k: pkg.a.f(k), first=pkg.a.f)` and pinned that the default `pkg.a.f` stays as written;
    after the move `pkg/a.py` has no `f`, so the destination cannot import. It becomes a refusal: exit 1, stderr
    `[resolve]`, `[checks]`, `[references]`, `pkg/b.py:5: pkg.a.f would not resolve as it does now, so nothing was
    refactored; move it by hand`, no file changed *(user: "Refuse it"; found by codex)*. The lambda half of that case
    moves to a new case. The whole Python `dr-refactor` corpus is the false-positive test of
    the comparison. If a case that passed now refuses: STOP and show the user the case, the finding line and both
    fingerprint entries. Never change a golden, loosen a fingerprint rule or skip a file to make it pass. *(default)*
37. **Cost is measured, not assumed.** The comparison parses and binds every project file twice and copies the Python
    sources once. Measure `dr-refactor --timings move-symbol` (dry run) on this repo's `python/` project before and
    after; when the run takes more than twice as long or more than 5 s longer, STOP and ask the user. Fallback idea to
    raise then: compare only the changed and moved files, the files spelling the moved name, and, to a fixed point,
    the files spelling any top-level name a compared file no longer binds. *(default)*
38. **Not in this change**, all in DEV-2350: the module finder checked against Python's own import machinery, a
    test harness that imports a fixture project before and after a move and compares what its modules hold, the
    comparison for module renames (`rename` without a locator, which runs through `rename_map`), and what the
    comparison cannot see (string annotations and type comments, an import that moves in or out of a block, import
    cycles, file headers, a read that changes between two same-named bindings of nested scopes). *(user: "a separate
    issue for the rest")*
39. **Codex review of this plan** (2026-11-18), beyond the findings folded in above as *(codex)*:
    - A scope path and ordinal for `("local", name)` and `("opaque", name)`: *rejected (codex)*. A move edits nothing
      inside a nested scope except a chain it rewrites, and that chain's value before is a declaration or module, so
      a capture by a local already shows as a changed value. Listed in DEV-2350 as a known gap.
    - "Task 9.2's line should not be 2": *rejected (codex)*. Probed on today's code: the moved text lands above
      `len = 3` (a read inside a function body is no declaration-time dependency), so `len` is read on line 2.
    - One inventory row per case: *rejected (codex)*. `INVENTORY.md` rows list several case ids each and
      `tests/test_conformance.py` checks ids, not rows; task 9.4 now says both ids go in backticks.
    - The exact function to patch for the rename fault and the typed `verify` signature: folded into task 9.6 and
      decision 35. *(codex)*
40. **Outcome of the false-refusal test and the cost measurement** (pr-implement, 2026-11-18). Six existing cases or
    tests refused and the cost was over decision 37's limit; each item below is the user's call.
    - *Agreement is judged on canonical values* (amends decisions 31–32): a name, or an attribute of a module, with
      several bindings has a value when every binding has the same canonical value, and is `"?"` otherwise; an
      attribute of a module is read from that module's own bindings. Keeps
      `refactor-move-symbol-qualified-self-reference-overload` passing. *(user)*
    - *A module-level `__getattr__`* (amends decision 31): an attribute that a module defining `__getattr__` does not
      bind has no value, so a chain's value stops at that module, as rule 2 of decision 16 keeps the use. Keeps
      `refactor-move-module-package-binds-getattr` passing. *(user)*
    - *Order is compared in one direction* (amends decision 33 and part (b) of the requirement): a read counted
      `"bound"` after the move and `"not-yet"` before it, with the same value and tail, is no difference. Keeps
      `refactor-move-shadowing-rebound-import` passing. *(user, approved wording of part (b))*
    - *Refused from now on*: `refactor-move-symbol-import-rebound-in-source` (golden changed to the refusal);
      `refactor-move-shadowing-global-nonlocal` (golden changed to the refusal; the new case
      `refactor-move-shadowing-global-nonlocal-read`, the same fixture without `sub = None`, keeps pinning the
      rewrite); and the unit test of a destination alias of the moved symbol that a needed import takes
      (`tests/test_move_edits.py`, renamed, now expects the refusal). *(user)*
    - *Cost*: `--timings` `total` on `python/` (236 files) went from 0.08 s to 2.65 s. Taken: every file is still
      compared, but parsed once. The resolver takes the project's own parsed module for a file
      (`Resolver(parsed=...)`), and the project after the move adopts the module of each file the move neither
      writes nor moves (`MoveProject.adopt`). Measured after: 1.61 s. Rejected: decision 37's fallback of comparing
      a subset of the files. *(user)*

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

- [The resolver comparison refuses a move that is correct] → every existing move golden must stay byte-identical
  (decision 36); a false refusal stops the work for the user, never a loosened rule.
- [The comparison shares the resolver with the planner, so a resolver bug passes both] → accepted here; DEV-2350 adds
  oracles that share no code with it.
- [The comparison reads every file twice and copies the sources] → measured (decision 37), with a recorded fallback.

## Migration Plan

Build the new path beside the old (`move_edits` on the resolver, rope's path untouched), run the differential, stop
and ask on any difference not pinned by a manual golden, then switch `rope_refactor` to the new path and delete the
old one. No rollback beyond git; rope stays installed until DEV-2312.
