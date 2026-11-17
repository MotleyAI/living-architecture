## Context

A Python module rename runs in `run_module_rename` (`refactor/module_rename.py`), which `RenameMap.run` dispatches to
after `resolve` and `checks` when the first entry is a module; `RenameMap.resolve` refuses `len(out) > 1 and any(r.is_module())`.
That second pipeline duplicates keep resolution, the binding check, output, the stub and the taken check, and
"`rename` equals its one-entry map" holds only because the two paths are kept in step by hand.

Structural cause: two code paths for one refactor. Fix: one path. A module rename is one more entry kind of the map's
union; the map carries moves wherever it carries edits.

Principles that apply (`architecture/system.arc42.md`; `python.refactor` has no arc42 file of its own):
1. Twins: identical observable behaviour, decided by the conformance corpus. The module entry form, routing, the
   invalid forms and the TypeScript refusal are neutral cases run through both invoking twins.
2. Parameters, texts and command surfaces come only from `shared/`: the schema, the new finding and the help text.
3. Language-specific code stays in `refactor` (and `lang`).
4. No target-repo code is imported or run.

No arc42, LikeC4 model or `index.yaml` edit: the spec delta modifies the existing `refactor` capability, which
`python.refactor` owns.

## Goals / Non-Goals

**Goals:**
- `{module: PATH, new_name: N}` entries, and import-located module renames, computed in one map beside any other
  entries: one snapshot, one binding check over every edit and move, one combined report, one all-or-nothing write.
- Moves inside a moved package compose.
- `--keep` and `--stub` across a map as for a single module rename.
- `rename --file F` with no locator is the one-entry map `[{module: F, new_name: N}]`, by construction.
- The TypeScript twin accepts the form and refuses it with a finding.

**Non-Goals:**
- Moves into another package (`move-module`).
- TypeScript module renames (DEV-2325).
- A directory form of `module:` (a package is named by its `__init__.py`, as with `rename --file`).
- `--stub` for packages, namespace packages or library-module aliases.

## Decisions

1. **Module renames join the union; `run_module_rename`, the `module_rename` callback and the `file_modules` flag
   go.** `ModuleRename` becomes a `MapRename` yielding edits and one move; `RenameMap` carries moves through merging,
   both name-conflict passes, keeps, site resolution, baseline, output and stubs. (default: structural fix — one path
   instead of two kept equal by hand)
2. **Nested moves compose.** A module entry inside a package another entry moves is supported: one final path per
   original file from every surviving move, independent of entry order; moves made innermost first; each entry
   prints its own `rename from`/`rename to` pair from its old path to its new name beside it. (user: refusing it had
   only a smaller diff for it)
3. **A taken new name is a cheap check in `checks`.** Pre-map, pure AST: `[resolve]`, `[checks]`, `refactor.name-conflict`,
   no reference search; the four `refactor-rename-module-onto-*` goldens drop `[references]`. Alternative: report it
   in `conflicts` with every other name conflict (one home, fuller combined report, but a discarded reference search).
   (user, A)
4. **TypeScript module renames are tracked as DEV-2325**, created with its worktree branched from this branch; the
   TypeScript refusal's code comment points to it. (user)
5. **`--stub` covers every moved module file** and is refused with `refactor.stub-not-module` when the run renames no
   module or any module rename is of a package, a namespace package or a library module's alias; a kept move gets no
   stub. (default: as a single rename; codex finding 2 added the alias case)
6. **`module:` names a source file**, a package by its `__init__.py`, mirroring `rename --file`. (default: a
   directory form would be an extension)
7. **Module entries print their `references` progress item**; a lone module rename gains one stderr line; module
   entries join no `rules` group. (default: one path, no special case)
8. **The TypeScript refusal precedes any phase line**, one line per module entry in index order, like
   `refactor.map-invalid`. (default)
9. **One final-path map for every binding check.** `BindingCheck.conflicts` reverses its move map, so it gets one
   injective map of original file → final path built from every surviving move; two files ending at one path are a
   `refactor.name-conflict`. Tested in both entry orders, three levels deep, and with two moves converging. (codex)
10. **The routing requirement is in the delta**: a map's language comes from each entry's `file` or `module`, with
    today's unsupported-extension, missing and outside-project findings and precedence. (codex)
11. **The schema form is language-neutral**: `module` is a source-file path; being a Python module is decided after
    routing, and the TypeScript twin refuses module entries before anything else. (codex)
12. **One module identity.** A path-named module entry and an import-located module rename resolve through one
    canonical identity (source-folder normalisation, package directory), so they merge or collide reliably: a module,
    an `__init__.py`, a module under a namespace package. (codex)
13. **Keeps on nested moves.** Each move is kept by its own path's keep; a directory keep also keeps the moves under
    it (the existing directory-keep rule); a module whose own move is kept still moves with its package, under its old
    name. (codex finding 6 folded; its "a kept package does not keep a child move" part rejected, since a directory
    keep covers every file under it by the existing `--keep` requirement)
14. **Equivalence suite.** Every `refactor-rename-module-*` case also runs as its one-entry map, byte-identical. (codex)
15. **Contract coverage.** `refactor.map-module-unsupported` is produced by a named neutral golden, listed in
    `conformance/INVENTORY.md`; `scripts/sync-shared --check` and both twins' conformance runs verify. (codex)

Approved wording:
- Finding `refactor.map-module-unsupported`: `'{map}: entry {index} renames a module, which a TypeScript rename-map
  cannot do yet, so nothing was refactored'` (user, approved wording)
- `shared/cli.yaml`, `rename-map` positional `map` help: `'the map file: entries {file, symbol | line [col] | offset,
  new_name | retarget} or {module, new_name}'` (user, approved wording)
- `shared/schema/rename-map.schema.json`, appended to the description: `Or a module entry: module (a source file
  relative to --project; an __init__.py names its package) and new_name, nothing else.` (user, approved wording)
- `plugin/skills/deterministic-refactor/SKILL.md`, replacing the rename-map sentence: `` `rename-map MAP` reads a YAML
  list of `{file, symbol, new_name}`, `{file, symbol, retarget}` or, for a Python module, `{module, new_name}` entries
  (paths relative to `--project`), resolves every entry before renaming any, and writes all or nothing. `` (user,
  approved wording)
- `docs/deterministic-refactoring.md`, replacing the rename-map sentence's opening: `` `rename-map MAP` applies a YAML
  list of rename, retarget and Python module (`{module, new_name}`) entries as one refactor: every entry resolved
  before any is renamed, one diff, one refusal report, written all or nothing. `` (user, approved wording)

## Risks / Trade-offs

- [Every lone module-rename golden changes (progress item; taken cases lose `[references]`)] → manual goldens edited
  by hand with the reason in the commit; the equivalence suite pins `rename` = its map.
- [Keeping a moved module's file leaves its importers rewritten to the new path] → existing single-rename behaviour,
  unchanged here.
- [Composed moves and the baseline realignment] → the realignment maps paths through the same final-path map.
