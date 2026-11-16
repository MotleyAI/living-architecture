## Context

See proposal.md (Why). Probed on this branch (all exit 0 today, both twins unless marked): issue capture (`old` →
`next` writes `next + next`); issue duplicate member (`C.old` → `next` beside `next()`); shadowing (`old2` → `nxt`
captures an outer `nxt` the function reads); a direct importer's own `next` captured (`import {old}` → `import
{next}`); Python only: `old` → `f` beside `def f` (no check at all); Python only: module `pkg/a.py` → `b` while
`pkg/b.py` exists ("rename from pkg/a.py to pkg/b.py", and `from pkg import a` → `from pkg import b` beside a local
`b`). TypeScript keeps a re-export as a boundary (`export { next as old } from './m.js'`, importers of the barrel
unchanged).

The checks today, each a partial re-implementation of name resolution:
- TypeScript `checkNameConflict` (`node/src/refactor/rename.ts`): a clash only when the declaration found by
  `resolveName(newName)` at a rewritten site lies in a scope that declares the renamed symbol; skips every member
  rename; runs before `--keep`.
- TypeScript `checkConvergence` with the hand-written `bindingScope` / `blockOf` / `blockScoped`.
- Python `RenameMap.check_convergence` (`rename_map.py`) and the parameter scan (`_variable_sites` in
  `rename_union.py`, raised from the parameter seeds).
- Unchanged and out of this change: the key/keyword collision check (`_conflict` in `rename_union.py`, the
  literal rename's `check_conflicts`), move-symbol's `NameConflict`, retarget's `retarget-shadowed` /
  `retarget-override`.

Principles that apply (`architecture/system.arc42.md`; `python.refactor` has no arc42 of its own):
1. Twins: every shape both languages share is a paired conformance case; Python-only and TypeScript-only shapes are
   adapter cases.
2. Shared contract: the existing `refactor.name-conflict` text is reused; the Python implicit root's member names are
   a language fact in `shared/languages.yaml`.
3. Language-specific code only in `lang` and `refactor`: both resolvers live in `refactor`.
4. No target-repo code runs: Python uses `symtable` and `ast` (compile, never execute); TypeScript uses the checker.

Spec attachment: `refactor`, owned by `python.refactor`. No model or arc42 edit; no new import arrow is expected
(`la-arch-check` confirms).

## Goals / Non-Goals

**Goals:**
- Symptom: a rename writes code in which a name means something else, or two members share a name. Structural cause:
  no single model of what each name means, only partial checks. Fix the cause: one binding-preservation check
  (re-resolve over the edited code, compare with the original) and one member-namespace check, in one code path per
  twin, replacing every partial rename conflict check, so a new scope shape or name kind cannot slip through one
  check's gap.
- Both issue shapes refuse in both twins, plus shadowing (builtins included), import collisions, re-export and
  star-import chains, member collisions across the whole hierarchy and the implicit root, Python module renames onto
  an existing name, and kept sites that would rebind.

**Non-Goals:**
- Key/keyword collisions, move-symbol conflicts, retarget's own findings: unchanged.
- Members added from outside the class or by `setattr`.
- A performance guard test (decision 26).

## Decisions

1. **One binding-preservation check plus one member-namespace check replace every rename conflict check** (TS
   `checkNameConflict`, `checkConvergence` and its `bindingScope`/`blockOf`/`blockScoped`; Python
   `check_convergence` and the `_variable_sites` parameter scan). Alternative: extend each check, which keeps N code
   paths that must agree by hand. (default, structural)
2. **Shadowing, builtins included, is in scope.** (user)
3. **Member collisions cover ancestors and descendants**; TypeScript sides separate, Python one class namespace
   including `self` attributes. (user)
4. **Python module rename onto an existing module, package or `__init__` binding is in scope.** (user)
5. **Python star imports bind the source module's public names**: `__all__` when a literal list or tuple, else the
   non-underscore module-level names; non-project star imports ignored. (user)
6. **`--keep`: a dangling kept site is allowed; a kept site resolving to another declaration is refused.** Options:
   refuse rebinding only / exempt fully / check strictly. (user)
7. **Every inherited member counts, from library bases and the implicit root.** Options: all inherited / explicit
   library bases only / project only. (user)
8. **The Python implicit root's members are a list in `shared/languages.yaml`** (python: `root_members`), the union
   over the supported Python versions, with a drift test against the `builtins.pyi` of the typeshed the pinned
   basedpyright ships. rope's model has no `object`; reading typeshed at runtime depends on basedpyright's package
   layout and on version conditionals. Supersedes the plan's runtime typeshed read. (codex)
9. **Re-resolution after the edits**, not a before-only analysis of scope chains: independent of each language's
   scope rules. TypeScript: an overlay program over the edited texts (unchanged `SourceFile`s reused). Python:
   the AST scope model `static_resolver` already uses for patch targets (Python's own rules, checked against
   `symtable` by the resolver test) over each edited source; import bindings are module-local declarations, so cross-module identity is
   only needed for star imports. A class body reads a name it binds only once a binding may have run: a read that no
   binding of the name in the class body runs before (a binding runs once its statement has evaluated what it binds: an
   assignment after its value, a walrus after its value, a `for` or `with` target and an `except` or `case` capture
   before the body they open, a `def` or `class` after its whole statement; a `del` is not tracked), nor in a loop of
   the class body whose repeated part holds the read (a `while` statement's condition and body, a `for` statement's
   target and body), resolves as the module's global, then the builtin (enclosing functions are skipped, as `LOAD_NAME`
   does); a read a binding may precede (conditionally or not) means both the class binding and the global one. (user:
   order-aware class bodies) An edited Python source that does not parse refuses with `refactor.cannot-rename`.
   (default)
10. **Finding site**: in original-code coordinates, the first by project-relative path then character offset among:
    an existing declaration of the new name that a rewritten occurrence or a renamed declaration would meet; an
    existing occurrence whose declaration would change; the declaration a kept occurrence would resolve to; for
    entries meeting, the earlier entry's first declaration; for a member declared outside the project, the renamed
    declaration's own site. Keeps the existing goldens and `node/test/rename-map.test.ts` (parameter property plus
    field → line 4; two catch variables allowed). (default; codex: original coordinates)
11. **Conflicts are checked after `--keep`, before the blind-spot and stand-in refusal**, in both twins (TypeScript
    checks before `--keep` today). (default)
12. **Maps: each `new_name` entry alone against the code before the map, in map order, then all entries together.**
    The per-entry pass is the existing rule "name-conflict checks run against the code before the map, so swaps and
    chains refuse" (DEV-2295 decision 14) in its general form; the combined pass catches entries that meet or capture
    each other and replaces both convergence checks. (default)
13. **Retarget entries**: their rewritten references are expected to resolve to the target (renamed by another entry
    or not); they keep their own findings; retarget's kept re-exports are not `--keep` sites. (default)
14. **Key/keyword collision and move-symbol conflicts are out of scope.** (default)
15. **TypeScript re-export boundary respected**: a barrel importer binding the new name keeps the old name, so it is
    no conflict. (default, after merging DEV-2296)
16. **Python class-body members come from `members.member_declarations`**; properties and annotated fields
    (dataclass, Pydantic) count; ancestors are the whole MRO; library bases from rope's model; `setattr` and
    attributes set from outside the class do not count. (default; codex 9 in part)
17. **Spec form**: the binding and member requirements are ADDED; the rename-map, Python parameter and Python
    rename-references requirements are MODIFIED. (default)
18. **The Python parameter rule follows binding preservation**: a nested binding of the new name that changes no
    reference's meaning is no longer a conflict; `test_type_parameter_of_the_new_name_is_a_conflict[nested]` is
    aligned to expect exit 0. Options: relax (one rule) / keep the strict scan as well (two code paths, a
    Python-only rule). (user; codex 1)
19. **TypeScript identity is the resolved symbol's declaration set**, each declaration keyed by file, its original
    span (mapped through the edits) and its syntax kind; aliases followed to their target. Cases for overloads and
    declaration merging. (codex)
20. **TypeScript meanings**: each occurrence resolves with the meaning its position requires, and "a scope already
    binds the new name" applies per meaning: a type alias `next` beside a renamed constant is allowed; an interface
    renamed onto a class name merges into it and refuses. (codex)
21. **The occurrence set is every identifier spelled with the old or new name in every project source** (text
    prefilter), closed under re-export and star-import chains. (codex)
22. **Only resolver-backed edits enter the check**: references, declarations, import/export specifiers, shorthand
    values, Python forward-reference strings; `--docs` mentions, string members, `Literal` values, compound names and
    keys keep their own rules. (codex)
23. **Python module renames: the destination check runs before rope is asked for changes**; the binding check runs
    over rope's edits on a virtual post-move snapshot (old module path mapped to the new). (codex)
24. **The renamed set (hierarchy, overload group, `--with` stand-ins) is subtracted before the member collision
    test.** (codex)
25. **Extra cases** from the Codex review: Python class-body vs method lookup, comprehension iterable and walrus,
    `global`/`nonlocal`; kept declaration and kept reference; `--docs`; `Literal` members; re-export and star-import
    two-hop chains; overloads; declaration merging; type vs value; interface plus implementation; multiple
    inheritance; retarget plus rename in one map; relative import, namespace package and kept import for module
    renames. (codex)
26. **No performance guard test**: timing tests are flaky and the repo has none; the overlay program reuses unchanged
    source files and resolves only prefiltered identifiers (risk below). rejected (codex 16, the guard part)
27. **No basedpyright overlay for Python resolution**: `symtable` is Python's own scoping, import bindings are
    module-local declarations, star imports are modelled (decision 5); an LSP query per identifier adds cost and no
    resolution the lexical model lacks. rejected (codex 2)
28. **The combined map state is not the only check**: the per-entry pass is the approved DEV-2295 rule that swaps and
    chains refuse. rejected (codex 6)

## Risks / Trade-offs

- [The TypeScript overlay program is costly on large projects and maps (one per entry plus one combined)] → unchanged
  `SourceFile`s are reused, only the files an entry edits are re-parsed, and only prefiltered identifiers are
  resolved; the checker binds lazily.
- [Python `symtable` misses a binding form a later Python adds] → the resolver test runs on every CI Python and
  compares against `symtable` itself.
- [`root_members` drifts from typeshed when basedpyright is bumped] → the drift test fails on the bump.
- [Refusals become stricter (shadowing, library and root members)] → deliberate (decisions 2, 7); `--keep` and a
  different new name remain the way out.
