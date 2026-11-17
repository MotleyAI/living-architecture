## Context

See proposal.md (Why). DEV-2301 is merged to main and archived; this branch has merged origin/main, and DEV-2315's branch (WIP,
unarchived), whose `conflicts` phase and narrowed conflict checks it builds on. Today
(`python/src/living_architecture/refactor`):

- `rope_refactor.run_refactor` builds a rope `Project`; `rename_map.RenameMap` locates each entry with rope's `Rename`
  (`_renamer`, falling back to the language server's `definition`), keys it with `_key` (rope's definition location),
  detects modules (`_is_renaming_a_module`), locals (`_is_local`), methods (`is_method`) and parameters
  (`ParameterName`), and validates the new name (`validate_changes`: a Python keyword).
- `rename_union.SymbolRename` reads the occurrence index, sends the occurrences the checker resolves to nothing to rope
  (`RopeSites`, decision 6 of DEV-2301), and uses rope for the located declaration's line, field and function
  (`_located`, `_located_field`, `_function_at`, `_parameter_declarations`) and for module names (`libutils.modname`).
- `member_namespace.Hierarchy` evaluates class bases with rope (`evaluate.eval_node`) for the new-name conflict check,
  while the renamed hierarchy already uses the checker's class graph (`hierarchy.ClassGraph`, DEV-2301 decision 8).
- `retarget` uses rope for the target's definition, a module's attribute, a module's file and name, and the receiver
  module of `MOD.ALIAS`.
- Module renames are rope's `Rename.get_changes` (`rope_refactor._module_rename`), filtered by `--keep` over a line
  diff (`_kept`), checked by `_taken` and `BindingCheck`.
- `emit` prints rope `ChangeSet` descriptions; texts are decoded with rope's `read_str_coding`; offsets convert between
  the raw text and rope's newline-normalised text (`_raw_offset`, `_rope_offset`, `locators._text`).
- `static_resolver.Resolver` (Python scoping, module bindings, `from` and star imports, module attribute chains over
  first-party modules) already backs patch targets and `explicit_any`; `patch_targets.SourceFolders` finds modules.

Principles that apply (`architecture/system.arc42.md`; `python.refactor` and `python.lang` have no arc42 of their own):
1. Twins — the behaviour is Python-only except `--offset`, where the Python twin comes to match the npm twin; the new
   cases are `adapter` cases plus one `paired` case.
2. Parameters and texts only from the shared contract — `refactor.unresolved-name` lives in `shared/findings.yaml`.
3. Language-specific code only in `lang` and `refactor` — the new export fact in `lang`, everything else in `refactor`.
4. No target-repo code runs — the static resolver and the ported rules read files; the checker runs isolated as today.

Spec attachment: `refactor`, owned by `python.refactor`. No model or arc42 edit: no new import edge.

Symptom and structural cause: two project models (rope's and la's) and two resolvers (rope and basedpyright) feed one
edit set and must agree by hand; gap 1 of DEV-2301 (the conflict check on rope's class graph beside the hierarchy on the
checker's) is one instance, gap 2 (a name neither resolver resolves gets no outcome) another. The fix makes the class
impossible: one project model, and each question answered by exactly one resolver — the checker for anything typed, the
static resolver for scoping, imports and module chains, the AST for declarations.

## Goals / Non-Goals

**Goals:**
- No rope object, call or text form on the `rename` / `rename-map` / `retarget` path, symbol or module.
- Byte-identical stdout, stderr, exit code and written bytes on every existing Python rename, rename-map and retarget
  golden.
- Every occurrence of an old name that a rename examines gets an outcome (edit, blind spot, leftover, unrelated, or the
  new unresolved-name line).

**Non-Goals:**
- Moves (`move-symbol`, `move-module`): DEV-2311. They keep rope, its `ChangeSet` (converted to la's changes at their
  boundary), the walker-gap check and `refactor.rope-walk`.
- Removing rope, `rope_patches.py`, `refactor.rope-walk`, `compliance.rope-walk` and the `rope-walk` compliance check:
  DEV-2312.
- The TypeScript twin, except that its `--offset` behaviour becomes the shared spec.

## Decisions

1. **Unresolved names: the static resolver replaces rope; what it also cannot resolve is listed.** An occurrence the
   index resolves to nothing is resolved by `static_resolver`: a renamed declaration (or the renamed module) → edit;
   another declaration → unrelated; nothing → `refactor.unresolved-name`. "Nothing" is a name bound nowhere, or bound by
   an import of a module neither the checker nor the source folders hold; a resolved local, parameter or attribute is
   never listed (member accesses are never in this set). Alternatives: static resolver without the line (DEV-2301
   gap 2 stays: a skipped site leaves no trace and no gate catches it); no fallback (renames that work today become
   leftovers). (user)
2. **Wording.** `refactor.unresolved-name: '{path}:{line}: unresolved-name: {old} resolves to no declaration here, so it
   is left unchanged'` (user, approved wording)
3. **Module rename self-alias.** An `as` alias spelled exactly like the renamed module's last segment is renamed with
   every use it binds, as rope does (`refactor-rename-module-references` pins it); any other alias stays. (user)
4. **One change, one PR, four commit series** (project model; entry location; unresolved names and lookups; module
   renames), each landing only after its differential run is clean. The issue allows a PR or a commit series per step;
   the `/la:pr` flow is one branch per change. (default)
5. **la's project model.** Files from `routing.language_files`; texts from `Snapshot` (raw text, one per file);
   changes as `TextEdit`s plus a list of file moves; `Session` takes the project root. Verbatim ports of rope's
   `get_source_folders`, `libutils.modname` and `project.find_module` (precedence and ignored resources included) live
   in one module and back `BindingCheck`, `TargetResolver`, the static resolver's module finder, `_owners`,
   `_class_path` and retarget's module names. Each port is compared against rope directly (rope stays installed) over
   generated layouts: nested and namespace packages, a package beside a same-named module, `.pyi`, symlinks, duplicate
   dotted modules in two source folders. (default; precise port and comparison: codex)
6. **One read/write pipeline.** Symbol renames already decode with the PEP-263 cookie (else UTF-8) and write each
   file's text back in its encoding with every line ending kept; module renames join that pipeline instead of rope's
   (which decodes with a Latin-1 fallback and rewrites every line to the file's dominant newline). On a file with mixed
   line endings a module rename now keeps each line's ending (spec scenario "Module rename keeps line endings"); no
   golden holds such a file. rope's `read_str_coding` is ported verbatim. Round-trip tests: UTF-8 BOM, UTF-8 and
   Latin-1 cookies, an unknown cookie, CRLF, lone CR, mixed endings, no final newline. (default; folded from codex)
   A project file that does not decode (an unknown cookie, or bytes invalid in its encoding) is left unchanged by every
   rename, symbol or module. When its bytes hold an old name's UTF-8 spelling it is listed with `refactor.undecodable`
   on stderr, printed with the leftovers and sorted by path; a `--keep` covering the file drops its line, and the exit
   code is unchanged. (user)
   A leading UTF-8 BOM is decoded out of the text, as Python and basedpyright read the file, and written back; this
   fixes symbol renames, module renames and entry location in such a file, which all fail today. (user)
7. **la renders the diff.** Per file, `difflib.unified_diff` of the old and new text, both newline-normalised for
   display exactly as rope's `ChangeContents.get_description` does (`splitlines(True)`, `a/<path>`, `b/<path>`); a move
   as `rename from <path>\nrename to <path>`; blocks sorted and joined as `emit` does today. Only offsets stop
   converting; the display keeps rope's rendering so output stays byte-identical. Tested on the full emitted block:
   no final newline, empty file, CRLF and lone CR, non-ASCII paths, an edit plus a move, a realigned baseline.
   (default; full-block vectors: codex)
8. **Declaration at a site, one algorithm.** A locator's offset is first matched to the identifier token under it
   (else `refactor.cannot-rename`); if that token is a binding (def, class, every parameter kind including lambda,
   positional-only, keyword-only, `*args`/`**kwargs`; an assignment, augmented, annotated, walrus, `for`, `with`,
   `except`, `match` or comprehension target; `global`/`nonlocal`; an import alias; a `self.` attribute store in a
   method), it is that declaration, grouped with the same-named declarations of its scope as `symbol_path` groups them;
   otherwise it is a reference, resolved by the static resolver, else by the run's language server's `definition` at
   that position (started lazily, as `_renamer` does today). A reference resolving to declarations of more than one
   group, or to nothing, is `refactor.cannot-rename`. `--symbol` naming an import binding follows the static resolver to
   its declaration or module, except a binding DEV-2301 decision 22 matches by binding, which is the entry itself,
   keyed by its own site. (default; one explicit algorithm: codex)
9. **Kind and key from the declaration.** Module (a static-resolver module value, or the module file) → module rename;
   `ast.arg` → parameter; a declaration in a function, lambda or comprehension scope → local (only its file is
   searched); a def in a class body → method; a class-body or `self.` member → member. The canonical key is
   `(kind, rel, line, name)` of the group's first declaration (overloads, property accessors: the first def, as rope
   keys them); a declaration outside the project keys by the entry's site and renames nothing, as today (probe: a
   rename of `os.getcwd` or `len` prints an empty diff and exits 0). Keys stay AST-based: the index is exported only
   after the checks phase, which needs the merged entries, and DEV-2306 measured the AST key equal to rope's on 703
   entries. Duplicate-entry tests cover overloads, property getter/setter, conditional and repeated assignments, and an
   entry by import binding beside one by declaration. (default; index-based key: rejected (codex), reason above)
10. **The new-name conflict check on the checker's class graph.** The export's batched facts (DEV-2301 decision 4) gain
    one fact kind: for a class, its bases as the checker resolves them and, for each class of its MRO outside the
    project, whether it declares each of the run's new member names. The request carries every class of the candidate
    files (the renamed members' classes are among them), independent of how any file spells the new name, plus the
    classes of the files spelling a new member name (for project descendants). `MemberCheck` reads `hierarchy.ClassGraph`
    instead of rope's `Hierarchy`; the implicit-root check stays. The fact is part of the request, so the cache key covers
    it. Cases: a library base declaring the new name, directly and through a transitive library base, where the library is
    installed only in the project's environment; a project ancestor reached through a base rope cannot evaluate.
    Closes DEV-2301 comment gap 1. The project classes declaring a new member name are still found once per name per
    run (DEV-2315 decision 8); the check runs in DEV-2315's `conflicts` phase. (default; full-MRO request: codex)
11. **Retarget's lookups on the static resolver.** The target's declaration (imports followed), module `M`'s attribute
    `N`, a module's file and name, and the receiver module of `MOD.ALIAS` come from the static resolver and the ported
    source folders. The issue named the index for receiver modules; a module receiver is exactly the static resolver's
    domain, it agreed with rope on every measured attribute site, and the index would need a new fact kind for it.
    (default)
12. **Module rename sites.** From import syntax and the static resolver, as the spec's module-rename paragraph lists
    them; `--keep` drops an edit on a kept line, and a kept module file is not moved while its importers are rewritten
    (as `refactor-rename-module-keep-file` pins); `_taken` and `BindingCheck` refuse as today (a taken name refuses
    before the `conflicts` phase; the binding check runs inside it with the full, unnarrowed check, as DEV-2315
    decisions 11 and 14 place it); `--with`/`--without` stay `refactor.not-stand-in`; `--docs` and `--unsure` have no
    effect on a module rename, as today (`_module_rename` calls rope without `docs`). A package `__init__.py` or package
    directory renames the directory. A module outside the project refuses as today. (default; `--docs` occurrences:
    rejected (codex), rope is called without `docs`)
13. **Alias entries match by binding (DEV-2301 decision 22).** An entry on a binding that DEV-2301 decision 22
    matches by binding keeps that rule: the checker's chain comes from the index. An occurrence the checker leaves
    unresolved (decision 1) is renamed for such an entry only when the static resolver's chain for it holds the
    entry's binding. (user)
14. **Renames no longer check walker gaps.** rope walks no module of a rename after this change; by DEV-2301 decision
    16's rule (refuse only for modules rope walks) the check stays for moves only. (default)
15. **`--offset` counts the file as read.** Code points of the raw text, CRLF and lone `\r` counted, as the npm twin's
    `locateOffset` and `shared/cli.yaml` ("0-based character offset") define it; the Python twin counted rope's
    normalised text, a twin divergence on CRLF files no golden pins. The requirement "TypeScript locators" becomes
    "Locators" for both twins, pinned by a `paired` case. (default)
16. **Differential method per series.** Build the new path beside the old; run both over every Python `rename`,
    `rename-map` and `retarget` conformance case, the unit fixtures that drive renames, new fixtures (CRLF, BOM, Latin-1
    cookie, mixed endings; the retarget matrix: direct and chained aliases, package `__init__` barrels, star exports with
    and without `__all__`, relative re-exports, an import cycle, `MOD.ALIAS` through a re-exported module; module renames
    with parenthesised, multi-line, backslash and semicolon imports, a package and a namespace package) and the DEV-1607
    map on a `git archive` copy of SLayer (dry run, `.venv` symlinked, never written). Compare normalised edit, move and
    finding sets and also raw stdout, stderr, exit code and the bytes `--apply` writes. Any difference stops the work for
    the user's call; then the old path is deleted. No golden is regenerated to absorb a difference. (default; raw
    comparison and the matrix: codex)
17. **Codex findings rejected or narrowed.** Limiting `refactor.unresolved-name` to sites "associated" with the renamed
    symbol: rejected, the line exists for exactly the sites no resolver associates (decision 1), and the spec pins that a
    resolved local is never listed. (codex, rejected)

18. **Docs wording (proposed; needs the user's OK of these exact texts before any edit).**
    - `plugin/languages/python.md` line 16: "`dr-refactor` resolves a rename's occurrences with the basedpyright bundled
      with la and computes every rename itself; rope computes moves."
    - `docs/deterministic-refactoring.md` lines 12–14: "Python resolves a rename's occurrences with the bundled
      basedpyright and computes every rename itself, and rope computes moves;"
    - `docs/refactoring-internals.md`: the rope row becomes "| rope (+ la's walker patches) | Computes `move-symbol` and
      `move-module`. | Moves are built on it. |"; a new row after it: "| la's static resolver | Resolves names, imports
      and module attribute chains by Python's scoping over the project's source folders: entry locations, the names
      basedpyright leaves unresolved, retarget's lookups and module renames. | It reads files only, so it resolves what
      the checker's configuration misses without running project code. |"; the paragraph's first sentence becomes "A run
      locates each map entry from the syntax tree and la's static resolver first." and its last "Module renames and
      moves never start the language server." stays. The diagram gains `static["la's static resolver"]` inside `la` with
      `rules --> static`.
    (pending user approval)
19. **Lambda parameters are renamed.** A lambda parameter is located like any other parameter (decision 8) and renamed with
    every use its lambda binds; rope refused it with `refactor.cannot-rename` only because it builds no lambda scope. The
    golden of `refactor-rename-param-lambda` and the cases of `test_lambda_shadowing_a_parameter_is_refused` change by hand
    to the rename. (user)

## Risks / Trade-offs

- [The static resolver decides edits, not only checks] → its scope stays bare names, imports and module chains; a member
  access is always the checker's; the differential run covers every site it decides.
- [A port drifts from rope on a layout the corpus lacks] → each port is compared with rope directly over generated
  layouts while rope is still installed (decision 5).
- [Small samples for module renames and retargets] → the new fixtures of decision 16; the SLayer map run.
- [The new export fact changes the export protocol] → verified preload as before; the command's self-test covers the
  new fact kind; the cache key includes the request.

## Migration Plan

No migration. Internal to the Python twin; the new stderr line appears only on sites that had no outcome before.
