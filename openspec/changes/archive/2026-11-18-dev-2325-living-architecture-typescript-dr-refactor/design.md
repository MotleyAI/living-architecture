## Context

The npm twin's `runEntries` (`node/src/refactor/rename.ts`) computes located symbol entries only; `renameMap`
(`node/src/refactor/typescript.ts`) refuses module entries, and `locate` throws `refactor.no-locator` for a locator-less
`rename`. `move-module` moves files in its own pipeline through the language service's `getEditsForFileRename`.
`dr-mock-lint` (`node/src/refactor/mocks.ts`) hard-codes the framework receivers, their modules and the factory-taking
mock calls. The Python twin refuses an invalid module new name only after `[references]` and `[conflicts]` (probed:
`--new-name a/b` prints `[references 1/1]`, `[conflicts]`, then `refactor.cannot-rename`).

Structural cause: one entry kind of the shared map schema has no path in one twin, and a second module-moving pipeline
exists beside it. Fix: one path. A TypeScript module rename is one more entry kind of `runEntries`, yielding specifier
edits and one move; `rename --file F` with no locator is the one-entry map; `move-module` and module renames share one
specifier routine (language-service edits plus mock module paths).

Principles that apply (`architecture/system.arc42.md`; the refactor nodes have no arc42 file of their own):
1. Twins: identical observable behaviour, decided by the corpus. Module cases become paired where TypeScript can
   express them; neutral cases stay neutral through both invoking twins.
2. Parameters, texts and command surfaces only from `shared/`: the mock facts, the help and schema wording, the removed
   finding.
3. Language-specific code only in `lang` and `refactor`.
4. No target-repo code runs: resolution is the compiler's.

No arc42, LikeC4 model or `index.yaml` edit: the delta modifies the existing `refactor` capability, which
`python.refactor` owns, and no import edge between nodes changes.

## Goals / Non-Goals

**Goals:**
- TypeScript module renames by `rename` without a locator and by `{module, new_name}` map entries, computed in the
  map's one snapshot beside symbol entries, checked together, written all or nothing.
- One specifier routine for module renames and `move-module`, mock module paths included.
- The module-entry conformance cases paired where TypeScript can express them.

**Non-Goals:**
- A locator on an import specifier as a module rename (Python's import-located form).
- Directory renames; an `index` file naming its directory.
- Jest `__mocks__/` manual-mock files following a renamed module.
- Python `patch()` targets on module renames.
- `--stub` for TypeScript.
- Namespace-imported framework receivers (`vitest.vi.mock`).

## Decisions

1. **Files only; `index.ts` is an ordinary file**; no directory form. Alternatives: A files only / B `index.*` names its
   directory (parity with `__init__.py`, but `index.ts` could then never be renamed as a file, and it needs composed
   moves and composed specifier edits). (user, A)
2. **`N` is the new stem, the extension kept** (a declaration file's whole declaration extension); refused with
   `refactor.cannot-rename` when empty, `.`, `..`, holding `/`, `\` or NUL, or ending in a TypeScript source or
   declaration extension. Alternatives: A stem rules / B also strip the file's own extension (one `N`, two meanings
   across twins) / C identifiers only (forbids `my-module`, `a.test`). (user, A)
3. **Taken = any sibling a specifier could also reach**: a file `N` + any TypeScript source or declaration extension,
   or a directory `N` (its `index` source, else its first file by path), line 1, in `checks`. Alternatives: A exact path
   only (misses `.tsx`/`.js`/`.d.ts` captures and a directory `N` captured by `./N`) / B any reachable sibling. (user, B)
4. **Mock module paths are rewritten**, in the one specifier routine shared by module renames and `move-module`.
   Alternatives: A leave (silently stale automocks) / B rewrite / C list as leftovers (same cost as B, fixes less).
   (user, B)
5. **Mock facts move to `shared/languages.yaml`** (typescript): the framework receivers with their modules and the
   calls taking a module path, each with its factory argument index where it takes one. `dr-mock-lint` reads its
   factory-taking calls from there; its output is unchanged. (default: structural — one list, principle 2)
6. **One path**: module renames are an entry kind of `runEntries`; `rename` with no locator is the one-entry map.
   (default: as DEV-2324 did for Python)
7. **An invalid module new name is a resolution failure in `resolve`** in both twins; Python's check moves there from
   after `[conflicts]`, pinned by a paired case. (default: a cheap check runs before any search)
8. **Local import bindings are left** (`import * as a`): no alias-spelled-like-the-module rule in TypeScript.
   (default: every TypeScript import binding is an alias; the brief scopes the rewrite to specifiers)
9. **New names meeting in one directory** (one stem) are refused in `conflicts`, naming the earlier entry's file at
   line 1. (default: mirrors Python's converging moves)
10. **Keeps, stand-in sites, `--stub`, progress and baseline mirror Python's module renames**: a whole-file keep of the
    moved file drops its move and its edits and counts as matched; a kept move leaves its importers rewritten; an
    all-module run refuses `--with`/`--without` with `refactor.not-stand-in` in `checks`; a module entry prints its
    `[references n/m]` line and joins no rules group; `--stub` is `refactor.stub-not-module`; the baseline is realigned
    through the move. (default)
11. **Paired where expressible, adapters otherwise; `refactor-map-module-typescript` and `refactor-ts-no-locator`
    removed.** (default: twin rule; tidy)
12. **Non-goals as listed above.** (default: outside the brief)
13. **The spec delta names every requirement it changes**, each MODIFIED text built on DEV-2324's. (codex)
14. **A shadowed `vi` is left; an undeclared `vi` is the global**, as `dr-mock-lint` treats it. (codex: an "unbound
    `vi`" test contradicted the rule)
15. **Project-references case** pinning one rewrite across referenced projects. (codex)
16. **Late-refusal atomicity case** for an `--apply` map of a module and a symbol entry. (codex)
17. **Same-statement cases**: a specifier and an imported name in one import compose; a retarget's removed duplicate
    import overlapping a module entry's specifier edit is `refactor.map-conflict`. (codex)
18. **Receiver forms are exactly `dr-mock-lint`'s** (a named import, aliased or not, and the unshadowed global); the
    namespace form is left, pinned by a test. (codex)
19. Rejected (codex): "module renames print no per-entry progress line" — DEV-2324's delta already makes a module
    entry print its line like any other; the paired `refactor-progress-map-module` pins it.
20. A relative `declare module` naming a moved file is rewritten like a mock module path; the language service's
    file-rename edits are computed with those names masked (same length), since it returns no edit while one exists
    (probed, TypeScript 6.0.3). (user, A)
21. Each rewritten specifier keeps its own extension style (none, or its extension), whatever the service infers from
    the file's other imports: the shared specifier routine corrects the service's edits. (user, A)
22. A tsconfig `files` or `include` entry naming a moved file is rewritten by the service's file-rename edits: the
    Workspace gives each project its tsconfig as a parsed JSON source, for module renames and `move-module` alike.
    (user, A)

Approved wording:
- `shared/cli.yaml`, `rename` help: `rename the symbol at a location, or with no locator the module --file names (its
  file moves and every import follows); Python: also on an import that names a module` (user, approved wording)
- `shared/cli.yaml`, `rename --file` help: `'file holding the symbol (with no locator: the module to rename)'` (user,
  approved wording)
- `shared/schema/rename-map.schema.json`, the description's last sentence: `Or a module entry: module (a source file
  relative to --project; a Python __init__.py names its package) and new_name, nothing else.` (user, approved wording)
- `plugin/skills/deterministic-refactor/SKILL.md`, replacing the sentences from "A Python `rename` located on" through
  "`{module, new_name}` entries": `` A `rename` given `--file` a module and no locator, or a Python `rename` located on
  an import that names a module, renames the module: its file (a Python package's directory) moves beside itself, a
  TypeScript module keeping its extension (`--new-name` is the new stem), and every import follows, while
  `move-module` only moves a module into an existing package under its own name. `--stub REMOVAL` (Python) leaves a
  stub at the old path from the repo's `refactor.python.moved_module_stub`. `rename-map MAP` reads a YAML list of
  `{file, symbol, new_name}`, `{file, symbol, retarget}` or `{module, new_name}` entries `` (user, approved wording)
- `docs/deterministic-refactoring.md`, the rename-map sentence's opening: `` `rename-map MAP` applies a YAML list of
  rename, retarget and module (`{module, new_name}`) entries as one refactor: `` (user, approved wording)

## Risks / Trade-offs

- [The service edits a tsconfig only when given it as a parsed JSON source; probed: today's `move-module` leaves a stale
  `files` entry] → decision 22; pinned by a case.
- [Mock specifier rewriting must match the language service's own import rewrite] → a case pins a mock string and an
  import of the same specifier in one file ending equal, relative and `paths`-mapped.
- [A `.mts`/`.cts` sibling blocks a stem whose `nodenext` specifier would not strictly collide] → accepted: the user
  picks another name.
- [A kept move leaves its importers rewritten] → existing Python behaviour, mirrored.
- [The paired cases and DEV-2324's still-open change] → DEV-2324's branch is merged in as it moves; its archive lands
  first, so every MODIFIED text here is built on its version.
