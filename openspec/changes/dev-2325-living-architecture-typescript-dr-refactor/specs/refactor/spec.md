## ADDED Requirements

### Requirement: TypeScript module renames
`rename --file F --new-name N` with no locator, and a `rename-map` entry `{module: F, new_name: N}`, SHALL rename the
TypeScript module `F`, a source file of any extension the registry gives TypeScript, a declaration file included. `F`
SHALL move to `N` followed by its own extension (a declaration file's whole declaration extension) in its own
directory. A directory and an `index` file SHALL get no special meaning: `F` is always the one file. In every project
the refactor computes a rename in, every specifier resolving to `F` (import and export declarations, `import()` calls
and types, `import x = require()`, `require()` in a JavaScript source, module declarations) SHALL be rewritten to name
the new path, keeping its form, together with every edit the language service makes for the move in other files; mock
module paths SHALL follow as "TypeScript module moves rewrite mock module paths" defines. Local names an import of `F`
binds SHALL be unchanged.

The module's old name SHALL be `F`'s file name without that extension. Its header SHALL be `refactor.rename-header`,
its move SHALL be printed as one `rename from`/`rename to` pair, and an edit in `F` SHALL be printed at `F`'s old path
and, with `--apply`, written before the move. A new name equal to the old name SHALL change nothing.

A new name that is empty, `.` or `..`, holds `/`, `\` or NUL, or ends in a TypeScript source or declaration extension
SHALL be refused with `refactor.cannot-rename` as a resolution failure. A module rename SHALL be refused with
`refactor.name-conflict` in the `checks` phase, before any reference search, exit 1, writing nothing, when `F`'s
directory already holds, in the code before the refactor, a file named `N` followed by any TypeScript source or
declaration extension (naming it at line 1), or a directory named `N` (naming its `index` source file at line 1, else
its first file by path); a file of another extension SHALL NOT count. In a map, module entries whose new names are one
name in one directory SHALL be refused with `refactor.name-conflict` naming the earlier entry's file at line 1, in the
`conflicts` phase.

`--stub` SHALL be refused in a TypeScript run with `refactor.stub-not-module` in the `checks` phase, exit 2. A file in no
project SHALL be refused with the outside-project finding. The type-check baseline SHALL be realigned through the move.

#### Scenario: Rename without a locator
- **WHEN** `--apply rename --file src/a.ts --new-name b` runs, `src/use.ts` holds `import { f } from './a.js'` and
  `test/t.ts` holds `export * from '../src/a'`
- **THEN** `src/a.ts` is at `src/b.ts`, the importers read `./b.js` and `../src/b`, stdout holds the rename header, the
  `rename from src/a.ts`/`rename to src/b.ts` pair and both diffs, and the exit code is 0

#### Scenario: Extension kept
- **WHEN** `src/x.d.ts` is renamed to `y` and `src/a.test.ts` to `c`
- **THEN** they move to `src/y.d.ts` and `src/c.ts`, and the second header names the old name `a.test`

#### Scenario: An index file is a file
- **WHEN** `src/lib/index.ts` is renamed to `main` and `src/use.ts` imports `./lib/index.js`
- **THEN** the file moves to `src/lib/main.ts`, the directory stays, and the import reads `./lib/main.js`

#### Scenario: Invalid new name
- **WHEN** a module rename's new name is `b.ts`, `a/b` or `..`
- **THEN** stderr is `[resolve]`, `[checks]` and `refactor.cannot-rename`, the exit code is 1 and nothing changes

#### Scenario: Name taken by a sibling
- **WHEN** `src/a.ts` is renamed to `b` in one project holding `src/b.tsx`, in one holding `src/b/index.ts`, and in one
  holding only `src/b/util.ts` and `src/b/zed.ts` under `src/b/`
- **THEN** each is refused after `[resolve]` and `[checks]` with `refactor.name-conflict` naming `src/b.tsx` line 1,
  `src/b/index.ts` line 1 and `src/b/util.ts` line 1, and nothing changes

#### Scenario: A sibling of another language
- **WHEN** `src/a.ts` is renamed to `b` and `src/b.json` and `src/b.css` exist
- **THEN** the rename applies

#### Scenario: Renamed to its own name
- **WHEN** `src/a.ts` is renamed to `a`
- **THEN** no file changes and the exit code is 0

#### Scenario: Local import names stay
- **WHEN** `src/a.ts` is renamed to `b` and `src/use.ts` holds `import * as a from './a.js'` and `a.f()`
- **THEN** the import reads `import * as a from './b.js'` and `a.f()` is unchanged

#### Scenario: Module renamed across project references
- **WHEN** a solution tsconfig references `core` and `app`, and `app` imports and re-exports `core`'s `src/a.ts`, which
  is renamed to `b`
- **THEN** each specifier in `app` is rewritten once, the output equals that of the one-entry map, and the exit code is 0

#### Scenario: Stub refused
- **WHEN** a TypeScript module rename runs with `--stub 2.0`
- **THEN** stderr is `[resolve]`, `[checks]` and `refactor.stub-not-module`, the exit code is 2 and nothing changes

#### Scenario: New names meeting in one directory
- **WHEN** a map renames `src/a.ts` to `c` and `src/b.tsx` to `c`, where no `c` exists
- **THEN** stderr's final report is `refactor.name-conflict` naming `src/a.ts` line 1 after `[conflicts]`, the exit code
  is 1 and nothing changes

### Requirement: TypeScript module moves rewrite mock module paths
A TypeScript module rename and `move-module` SHALL rewrite the module path of every mock call naming a moved file: a
call, on a receiver bound to a test framework, of a method the shared language facts list as taking a module path,
whose module argument is a string literal that resolves, by the program's module resolution from its file, to a moved
file. The path SHALL be rewritten as the language service rewrites an import of the same specifier in that file: a
relative specifier stays relative and keeps its extension style, and a `paths`-mapped one keeps its mapping. A receiver
SHALL be bound to a framework when it is a named import, aliased or not, of the framework's receiver from the
framework's module, or the unshadowed global of that name; any other receiver, such as a local of that name or a
namespace import's member, SHALL be left.

#### Scenario: Vitest mock paths
- **WHEN** `src/api.ts` is renamed to `client` and a test holds `vi.mock('../src/api')`, `vi.doMock('../src/api.js', f)`,
  `vi.importActual('../src/api')` and `vi.mock(import('../src/api'), f)`
- **THEN** each reads `../src/client` or `../src/client.js` in its own extension style

#### Scenario: Jest typed factory agrees
- **WHEN** a test holds `j.mock<typeof import('../src/api')>('../src/api', f)` with `j` imported as `jest` from
  `@jest/globals`, and `src/api.ts` is renamed
- **THEN** the type argument and the string both name the new module

#### Scenario: Mapped mock path
- **WHEN** the project maps `@/*` to `src/*`, a test holds `vi.mock('@/api')` and `import { get } from '@/api'`, and
  `src/api.ts` is renamed to `client`
- **THEN** both read `@/client`

#### Scenario: Receivers left
- **WHEN** a test binds a local `const vi = { mock: (p: string) => p }` and calls `vi.mock('../src/api')`, and another
  holds `import * as vitest from 'vitest'` and `vitest.vi.mock('../src/api')`
- **THEN** neither string changes

#### Scenario: Mock path of a moved module
- **WHEN** `move-module --module src/api.ts --dest src/lib` runs and a test holds `vi.mock('../src/api.js')`
- **THEN** the string reads `../src/lib/api.js`

## MODIFIED Requirements

### Requirement: Locators
In both twins, `--line` and `--col` SHALL be 1-based and `--offset` 0-based; columns and offsets SHALL count Unicode
code points of the file as read, every line terminator (`\r\n`, `\n`, a lone `\r`) included in an offset, and a column
SHALL count within its line excluding the line terminator. A line, column or offset out of range SHALL exit 1 with a
finding, whose count is the file's code points for an offset. `--symbol` SHALL locate as the symbol-path requirement
defines. No locator SHALL exit 1 with the no-locator finding, except in a `rename`, which then renames the module
`--file` names.

#### Scenario: Astral character before the symbol
- **WHEN** a line is `const s = "😀"; const foo = 1;` and `--line 1 --col 22` points at `foo`
- **THEN** `foo` is renamed

#### Scenario: Column out of range
- **WHEN** `--col` exceeds the line's length plus one
- **THEN** it exits 1 with the out-of-range finding

#### Scenario: Module rename without a locator
- **WHEN** `rename --file pkg/sql/client.py --new-name cli2` runs with no locator
- **THEN** its output equals that of the rename located on an import of `pkg.sql.client`

#### Scenario: TypeScript module rename without a locator
- **WHEN** `rename --file src/a.ts --new-name b` runs with no locator
- **THEN** `src/a.ts` is renamed as a TypeScript module rename, not refused with the no-locator finding

#### Scenario: Retarget without a locator
- **WHEN** `retarget --file src/a.ts --target bar` runs with no locator
- **THEN** it exits 1 with the no-locator finding

#### Scenario: Module located on a dotted import
- **WHEN** a `rename` is located on `mod` in `import pkg.mod` or in `from pkg.mod import X`
- **THEN** `pkg/mod.py` is renamed as a module rename, and no name declared in it is renamed

#### Scenario: Offset after CRLF line breaks
- **WHEN** a file with CRLF line endings declares `foo` on its third line and `--offset` counts both characters of each
  earlier line break to reach it
- **THEN** both twins rename `foo`, and an offset one past the file's code points exits 1 with the out-of-range finding
  naming that count

### Requirement: TypeScript move-symbol and move-module
`move-symbol` SHALL apply the language service's move-to-file refactor for a top-level declaration into the
existing `--dest` file, rewriting every import of it. Every re-export of the moved symbol, named, default or
through `export *`, SHALL resolve to the new file. A location with no applicable move SHALL exit 1 with a
not-movable finding. `move-module` SHALL move a file or directory into the existing `--dest` directory and
rewrite every import of it, and every mock module path as "TypeScript module moves rewrite mock module paths" defines.

#### Scenario: Move a function with importers
- **WHEN** `--apply move-symbol --file src/a.ts --symbol foo --dest src/b.ts` runs and `src/c.ts` imports `foo` from `./a`
- **THEN** `foo` is in `src/b.ts`, `src/c.ts` imports it from `./b`, and the applied footer lists the changed files

#### Scenario: Default export and re-export
- **WHEN** the moved symbol is a default export re-exported by `src/index.ts`
- **THEN** every importer and the re-export resolve to the new file

#### Scenario: Barrel re-export
- **WHEN** `src/index.ts` has `export * from './a'` and `foo` moves from `src/a.ts` to `src/b.ts`
- **THEN** `src/index.ts` re-exports `foo` from `./b`

#### Scenario: Not movable
- **WHEN** the location is inside a function body
- **THEN** it exits 1 with the not-movable finding

#### Scenario: Move a directory
- **WHEN** `--apply move-module --module src/util --dest src/lib` runs
- **THEN** `src/util` becomes `src/lib/util` and every import of it is rewritten

#### Scenario: Move a mocked module
- **WHEN** `--apply move-module --module src/api.ts --dest src/lib` runs and a test holds `vi.mock('../src/api')`
- **THEN** the test reads `vi.mock('../src/lib/api')`

### Requirement: Member renames refuse on unclassified stand-ins
The renamed hierarchy SHALL be every declaration the rename renames with hierarchy on (Python: every member
declaration of OLD whose roots meet the located declaration's roots, where the roots of a declaration in class `C`
are the roots of OLD's declaration in each direct base of `C` that has OLD as the checker resolves it, or the
declaration itself when no direct base has OLD; TypeScript: the declarations
the language service's rename returns, merged interface declarations included), whether or not `--no-in-hierarchy` is
given, joined with the hierarchy of every `--with` stand-in. A stand-in SHALL be a class (Python) or a class,
interface or type literal (TypeScript), declared in a project source file of the rename's language and outside the
renamed hierarchy, that declares a member named OLD. Object literals SHALL NOT be stand-ins.

A member rename with any stand-in that is neither `--with` nor `--without` SHALL print one `refactor.stand-in` line
per stand-in member declaration on stderr, sorted by path, line and column and after any blind-spot lines, print
nothing on stdout, write nothing and exit 1, with or without `--apply`.

`--with PATH:LINE` and `--without PATH:LINE` (each repeatable) SHALL classify every stand-in member declared on that
line, together with that stand-in's own hierarchy. A `--with` stand-in SHALL be renamed in the same run: its
hierarchy joins the renamed hierarchy, and every rule of the rename (references, keyed rewrites, string-member
forms, `--docs`, `--keep`, blind spots) SHALL run once over the joined set, on one snapshot of the files, identical
edits merged. A `--without` stand-in SHALL be unchanged. A `--with` or `--without` naming no existing file or line
SHALL print `refactor.site-missing` in the `checks` phase. One whose line holds no stand-in member declaration of this
rename SHALL print `refactor.not-stand-in` at site resolution, which stops the run: nothing is written and the exit
code is 2. A module rename, in either language, has no stand-ins: when every entry of the run is a module rename, each
`--with` and `--without` site SHALL print `refactor.not-stand-in` in the `checks` phase; otherwise the sites SHALL be
classified by the run's other entries as above.
A TypeScript stand-in member declared by a computed name SHALL be classified by `--without` like any other;
`--with` naming its line SHALL print `refactor.computed-stand-in` at site resolution, write nothing and exit 2.

#### Scenario: Cast stand-in refuses until classified
- **WHEN** `StorageBackend.get_model` is renamed and `class _ModelReadCache` (no base in the hierarchy) defines
  `get_model` and is used as `cast(StorageBackend, _ModelReadCache(...))`
- **THEN** stderr's final report is the `refactor.stand-in` line naming `_ModelReadCache.get_model` with its path and
  line, the exit code is 1 and no file changes

#### Scenario: --with renames the stand-in in the same diff
- **WHEN** the same rename runs with `--with <that path>:<that line>`, and a module calls `c.get_model()` with
  `c: _ModelReadCache`
- **THEN** the diff renames both hierarchies' declarations and every call through either, and the exit code is 0

#### Scenario: --without leaves an unrelated class
- **WHEN** `class Unrelated` also defines `get_model` and the rename passes `--without` its line
- **THEN** `Unrelated.get_model` and calls through `u: Unrelated` are unchanged

#### Scenario: Shared references across several --with stand-ins
- **WHEN** two stand-ins are passed with `--with` and a `--docs` mention and a call site are reached through both
- **THEN** each site is rewritten once and the exit code is 0

#### Scenario: Classification line without a stand-in
- **WHEN** `--with` names an existing line that declares no stand-in member of this rename
- **THEN** stderr holds the `[rules]` lines and no `[conflicts]` line, the final report holds `refactor.not-stand-in`
  naming that site, the exit code is 2 and no file changes

#### Scenario: Classification site on a Python module rename
- **WHEN** a Python module rename passes `--with pkg/use.py:3`
- **THEN** stderr is `[resolve]`, `[checks]` and `refactor.not-stand-in` naming `pkg/use.py:3`, no `[references]`
  line is printed, the exit code is 2 and no file changes

#### Scenario: Classification site on a TypeScript module rename
- **WHEN** a TypeScript module rename passes `--with src/use.ts:3`
- **THEN** stderr is `[resolve]`, `[checks]` and `refactor.not-stand-in` naming `src/use.ts:3`, the exit code is 2 and
  no file changes

#### Scenario: Classification site on a map with a module entry
- **WHEN** a map renames module `pkg/a.py` and method `A.save`, and passes `--without` the line of a stand-in
  declaring `save`
- **THEN** the stand-in is classified, `A.save`'s hierarchy and the module are renamed and the exit code is 0

#### Scenario: Two stand-ins on one line
- **WHEN** one line declares two stand-in members named OLD and `--without` names that line
- **THEN** both are classified and neither is reported

#### Scenario: Hierarchy flag off
- **WHEN** `A.run` is renamed with `--no-in-hierarchy` and `B(A)` overrides `run`
- **THEN** `B` is not reported as a stand-in

#### Scenario: Python diamond and mixin hierarchy
- **WHEN** `A.run` is renamed, `B(A)` and `C(A)` override `run`, `D(B, C)` overrides it, and an unrelated mixin
  `M` declaring `run` is a base of `E(M, A)`
- **THEN** `A.run`, `B.run`, `C.run` and `D.run` are renamed, and `M.run` is reported as a stand-in

#### Scenario: TypeScript structural class and object literal
- **WHEN** interface `Store.getModel` is renamed, `class Fake { getModel() {} }` does not implement `Store`, and an
  untyped constant holds `{ getModel() {} }`
- **THEN** `Fake.getModel` is reported as a stand-in and the object literal is not

#### Scenario: Computed-name stand-in
- **WHEN** interface `Store.getModel` is renamed and `class Keyed { [KEY]() {} }` declares it through
  `const KEY = 'getModel'`
- **THEN** `Keyed.getModel` is reported as a stand-in; `--without` its line classifies it, and `--with` its line
  prints `refactor.computed-stand-in` at site resolution, writes nothing and exits 2

### Requirement: --keep leaves sites untouched
`dr-refactor rename` SHALL accept `--keep PATH[:LINE]` (repeatable). PATH SHALL be resolved against the working
directory to a real path under the project; a directory SHALL match the files under it by whole path components.
Every edit the rename would make on a kept line, in a kept file or under a kept directory SHALL be dropped,
whichever rule produced it, and a blind spot there SHALL NOT block the rename. A `--keep` naming no existing file,
directory or line SHALL print `refactor.site-missing` in the `checks` phase, and a line keep whose line holds no old
name SHALL print `refactor.keep-unmatched` there (see the cheap checks).

At site resolution, a keep that matched no edit and no blind spot SHALL be decided by its form:
- a whole-file or directory keep (no `:LINE`) leaves the outcome as asked: it SHALL print `refactor.keep-unneeded`
  naming it on stderr, and the run SHALL go on and, with `--apply`, write;
- a line keep SHALL be refused, with `refactor.keep-unmatched-near` naming the edited line of its file nearest to the
  kept line, else `refactor.keep-unmatched` when its file holds no edited line. An edited line is the start line of
  an edit the run writes, after every keep is applied; of two edited lines equally near, the earlier SHALL be named.
  Every such keep SHALL be reported, nothing SHALL be written and the exit code SHALL be 2.

Keeping a declaration SHALL NOT keep its references.

A whole-file keep of a module file a module rename moves, in either language, or a keep naming the directory of a Python
package it moves, SHALL drop that move and every edit in that file or under that directory, and SHALL count as matched;
a directory keep SHALL also drop the moves of the modules and packages under it. A module whose own move is kept SHALL
still move with a package another entry moves, under its old name. In a `rename-map`, every keep SHALL be resolved
once, over every entry's final edits and moves.

#### Scenario: Back-compat line kept
- **WHEN** `Storage.get_model` is renamed with `--keep tests/test_compat.py:12`, where line 12 calls
  `storage.get_model("m")`
- **THEN** line 12 is unchanged and every other reference is renamed

#### Scenario: Kept file and directory
- **WHEN** the rename passes `--keep tests/compat` and `--keep tests/test_shim.py`
- **THEN** no file under `tests/compat/` or `tests/test_shim.py` changes, while `tests/compatible.py` is renamed

#### Scenario: File keep and line keep together
- **WHEN** the rename passes both `--keep a.py` and `--keep a.py:3`
- **THEN** `a.py` is unchanged and the exit code is 0

#### Scenario: Unneeded file keep
- **WHEN** a rename runs with `--apply` and `--keep src/compat.py`, a file spelling the old name where no edit and no
  blind spot of the rename lands
- **THEN** stderr holds `refactor.keep-unneeded` naming `src/compat.py` after the last `[rules]` line and before
  `[conflicts]`, the rename is written and the exit code is 0

#### Scenario: Unneeded directory keep
- **WHEN** a rename runs with `--apply` and `--keep tests/compat`, a directory whose files hold no edit and no blind
  spot of the rename
- **THEN** stderr holds `refactor.keep-unneeded` naming `tests/compat`, the rename is written and the exit code is 0

#### Scenario: Unmatched keep
- **WHEN** `--keep src/a.py:9` names a code line spelling the old name where no edit of the rename lands, and the
  rename edits `src/a.py` on lines 4 and 12
- **THEN** stderr holds no `[conflicts]` line and ends with `refactor.keep-unmatched-near` naming `src/a.py:9` and
  line 12, the exit code is 2 and no file changes

#### Scenario: Unmatched line keep in a file without edits
- **WHEN** `--keep src/b.py:3` names a code line spelling the old name, and the rename edits nothing in `src/b.py`
- **THEN** stderr ends with `refactor.keep-unmatched` naming `src/b.py:3`, the exit code is 2 and no file changes

#### Scenario: Kept module file
- **WHEN** a Python module `pkg/old.py` is renamed with `--keep pkg/old.py`
- **THEN** the checks pass, the module is not moved and no `refactor.keep-unneeded` is printed

#### Scenario: Kept TypeScript module file
- **WHEN** a TypeScript module `src/a.ts` is renamed with `--keep src/a.ts`
- **THEN** the checks pass, the module is not moved, its importers are rewritten and no `refactor.keep-unneeded` is
  printed

#### Scenario: Kept importer line of a TypeScript module
- **WHEN** `src/a.ts` is renamed to `b` with `--keep src/use.ts:1`, where line 1 imports `./a.js`
- **THEN** the checks pass, line 1 is unchanged and every other importer reads `./b.js`

#### Scenario: Kept moved package
- **WHEN** a Python package `pkg/old/` is renamed with `--keep pkg/old`
- **THEN** the package is not moved, no `refactor.keep-unneeded` is printed and the exit code is 0

#### Scenario: Kept module inside a moved package
- **WHEN** a map renames package `pkg/sql/` to `db` and module `pkg/sql/client.py` to `cli`, with `--apply` and
  `--keep pkg/sql/client.py`
- **THEN** the module ends at `pkg/db/client.py` unchanged, its importers name `pkg.db.cli` (a kept move leaves its importers rewritten, as for a single rename), and the exit code is 0

#### Scenario: Kept package around a moved module
- **WHEN** the same map runs with `--apply` and `--keep pkg/sql` instead
- **THEN** no file under `pkg/sql/` moves or changes, no `refactor.keep-unneeded` is printed, and the exit code is 0

### Requirement: Rename maps apply many renames as one
`dr-refactor rename-map MAP` SHALL read MAP (a path relative to the working directory) as a YAML list of entries
valid against the shared rename-map schema: either `file` relative to `--project`, exactly one locator (`symbol`,
`line` with an optional `col`, or `offset`), and exactly one of `new_name` or `retarget` (a `symbol` in the same file);
or a module entry, `module` (a source file relative to `--project`) and `new_name`, and nothing else. An
invalid map SHALL exit 2 with `refactor.map-invalid` naming every invalid entry's index, in index order, printed by
the invoking twin before any routing; a map that cannot be read or is not a non-empty list SHALL name entry 1. It SHALL
take `rename`'s options other than the locator and `--new-name`, applying to every entry. All entries SHALL be of one
language, else exit 2 with `refactor.map-mixed-languages`; the map runs in that language's twin.

Every locator SHALL be resolved against the code before any entry is computed, so entries name old names. A module
entry SHALL rename the module its file is, exactly as `rename --file` with no locator does: in Python, a package's
`__init__.py` naming the package, and a module entry and an entry located on an import of the same module SHALL resolve
to one symbol; in TypeScript, the one file, as the TypeScript module-rename requirement defines, and two module entries
naming one file SHALL resolve to one symbol. A module rename, by a module entry or by a locator on a Python import,
SHALL be computed beside any other entries. Two entries resolving to one symbol with the same intent SHALL merge; with
different intents they SHALL be refused with `refactor.map-duplicate` naming both entry indexes, exit 2. Every entry
SHALL then be computed on one snapshot of the project, every rename rule running once over the union of the entries'
symbols, with one blind-spot scan for every member entry's old name and one combined refusal report, sorted as a single
rename sorts it. A site any entry rewrites SHALL NOT be listed as another entry's leftover. Identical edits SHALL merge;
every site two entries rewrite differently SHALL be refused with `refactor.map-conflict` naming the site and both
entries, exit 1, writing nothing. Name conflicts SHALL be checked first for each `new_name` entry alone against
the code before the map, in map order, so a swap or a chain of names inside one scope is refused, and then for all
entries' edits together, so entries that meet on one name or capture each other's references are refused. A retarget
entry's rewritten references SHALL resolve to its target, which another entry may rename. A retarget entry whose
target another entry renames SHALL write the target's new name.

Every path the map prints (headers, diffs, findings) SHALL be a path before the map. A module rename's move SHALL be
printed as one `rename from`/`rename to` pair, from its old path to its new name beside it; an edit in a file that a
move moves SHALL be printed at the file's old path and, with `--apply`, written before the move. Moves inside a package
another entry moves SHALL compose: every project file SHALL end at the path its own move and every surviving move of
a package holding it produce, in any entry order, and the moves SHALL be made innermost first. The name-conflict
checks SHALL see each entry's own move when it is checked alone, and every surviving move composed when all entries
are checked together, so two moves that end at one path, a moved module meeting a name another entry's edits bind in
its package, and a module's new name capturing a reference another entry rewrites are each refused with
`refactor.name-conflict`.

`rename` SHALL behave as a one-entry map with a `new_name`, and `retarget` as a one-entry map with a `retarget`;
their output SHALL equal that map's byte for byte. A `rename --file F --new-name N` with no locator SHALL be the
one-entry map `{module: F, new_name: N}`, in either language.

#### Scenario: Related renames in one pass
- **WHEN** a map renames `StorageBackend.get_model`, `StorageBackend.get_model_sync` and
  `StorageBackend.get_model(model_name)` and runs with `--apply`
- **THEN** stdout has one header line per entry in map order, one diff per changed file and the applied footer, and
  every reference of the three symbols is renamed

#### Scenario: Entries name old names
- **WHEN** a map renames method `A.old` to `new` and, in a later entry, parameter `A.old(x)` to `y`
- **THEN** both renames apply and the method is `new(self, y)`

#### Scenario: One combined refusal
- **WHEN** two member entries each meet one untyped receiver
- **THEN** stderr's final report lists both blind spots in path, line and column order, followed by one
  `refactor.blindspots` line, the exit code is 1 and nothing changes

#### Scenario: Duplicate entries
- **WHEN** two entries locate the same method with new names `a` and `b`
- **THEN** stderr ends with `refactor.map-duplicate` naming both entry indexes and the exit code is 2

#### Scenario: Conflicting edits
- **WHEN** one entry renames `Base.save` to `store` and another renames `Sub.save`, its override, to `keep`
- **THEN** stderr's final report holds `refactor.map-conflict` naming a shared site and both entries, the exit code is
  1 and nothing changes

#### Scenario: Swap in one scope refused
- **WHEN** a map renames parameter `f(x)` to `y` and `f(y)` to `x`
- **THEN** the rename refuses with the existing name-conflict finding of each entry and nothing changes

#### Scenario: Two entries converging on one name
- **WHEN** a map renames parameter `f(x)` to `z` and `f(y)` to `z`
- **THEN** the rename refuses with the existing name-conflict finding and nothing changes

#### Scenario: Two catch variables taking one name
- **WHEN** a TypeScript map renames the variables of two separate `catch` clauses to `err`
- **THEN** both renames apply and the exit code is 0

#### Scenario: Entries capturing each other's references
- **WHEN** one entry renames a module-level `a` to `z`, another renames a function's local `b` to `z`, and that
  function reads `a`, so that each entry alone is clean
- **THEN** the map is refused with the name-conflict finding and nothing changes

#### Scenario: Retarget beside a rename
- **WHEN** a map retargets alias `old_alias` to `target` and renames `target` to `renamed`, and a function reading
  `old_alias` binds no `renamed`
- **THEN** both entries apply and the function reads `renamed`

#### Scenario: Mixed languages
- **WHEN** a map holds a `.py` and a `.ts` entry
- **THEN** stderr is `refactor.map-mixed-languages` and the exit code is 2

#### Scenario: Invalid map
- **WHEN** entry 2 carries both `new_name` and `retarget`
- **THEN** stderr is `refactor.map-invalid` naming entry 2 and the exit code is 2

#### Scenario: Every invalid entry
- **WHEN** entries 2 and 4 are invalid
- **THEN** stderr is `refactor.map-invalid` naming entry 2 and then entry 4, through either invoking twin, and the
  exit code is 2

#### Scenario: Single rename equals its map
- **WHEN** `rename --file F --symbol Q --new-name N` and a map holding that one entry run on the same project
- **THEN** their stdout, stderr and exit codes are identical, through either invoking twin

#### Scenario: Another entry's rewrite is no leftover
- **WHEN** a map renames field `A.columns` to `fields` and `B.columns` to `cols`, and a file passes a
  `{"columns": ...}` dict to each class
- **THEN** each key is rewritten for its own class, no `leftover` line is printed and the exit code is 0

#### Scenario: Module entry beside symbol entries
- **WHEN** a map renames module `pkg/join_edges.py` to `relationship_edges` by `{module: pkg/join_edges.py}`, its class
  `JoinEdge` to `RelationshipEdge`, and function `pkg/use.py`'s `load` to `read`, where `pkg/use.py` holds
  `from pkg.join_edges import JoinEdge`, and runs with `--apply`
- **THEN** stdout holds the three headers in map order, the diff of `pkg/join_edges.py` at its old path, its `rename
  from`/`rename to` pair and the diff of `pkg/use.py`; `pkg/relationship_edges.py` declares `RelationshipEdge`,
  `pkg/use.py` holds `from pkg.relationship_edges import RelationshipEdge` and `def read`, and the exit code is 0

#### Scenario: TypeScript module entry
- **WHEN** a map renames `{module: src/join_edges.ts}` to `relationship_edges`, its class `JoinEdge` to
  `RelationshipEdge`, and function `src/use.ts`'s `load` to `read`, where `src/use.ts` holds
  `import { JoinEdge } from './join_edges.js'`, and runs with `--apply`
- **THEN** stdout holds the three headers in map order, the diff of `src/join_edges.ts` at its old path, its `rename
  from`/`rename to` pair and the diff of `src/use.ts`, whose import reads
  `import { RelationshipEdge } from './relationship_edges.js'`, and the exit code is 0

#### Scenario: Module entry located on an import
- **WHEN** a map renames function `pkg/use.py`'s `load` and, by a locator on `a` in `pkg/use.py`'s `import pkg.a`,
  module `pkg/a.py`
- **THEN** the function and the module are both renamed and the exit code is 0

#### Scenario: Two entries naming one module
- **WHEN** a map holds `{module: pkg/a.py, new_name: b}` and an entry located on `a` in `import pkg.a` with new name
  `c`; or `{module: pkg/sql/__init__.py, new_name: db}` and an entry located on `sql` in `import pkg.sql` with new name
  `db`
- **THEN** the first map is refused with `refactor.map-duplicate` naming both entries, and the second merges them into
  one rename of the package

#### Scenario: Two TypeScript entries naming one file
- **WHEN** a map holds `{module: src/a.ts, new_name: b}` twice, or `{module: src/a.ts, new_name: b}` and
  `{module: src/a.ts, new_name: c}`
- **THEN** the first map renames the module once with one header, and the second is refused with
  `refactor.map-duplicate` naming both entries

#### Scenario: A TypeScript map refused late writes nothing
- **WHEN** an `--apply` map renames module `src/a.ts` to `b` and function `src/use.ts`'s `load` to `read`, with a line
  keep that matches no edit
- **THEN** the run is refused with `refactor.keep-unmatched-near` or `refactor.keep-unmatched`, `src/a.ts` exists,
  `src/b.ts` does not, and every file is unchanged

#### Scenario: Specifier and imported name in one import
- **WHEN** a map renames module `src/a.ts` to `b` and its export `f` to `g`, and `src/use.ts` holds
  `import { f } from './a.js'`
- **THEN** the import reads `import { g } from './b.js'` and the exit code is 0

#### Scenario: A retarget's removed import meeting a module entry
- **WHEN** a TypeScript map retargets an alias so that an import of its target becomes a duplicate the retarget
  removes, and a module entry renames the module that import's specifier names
- **THEN** stderr's final report holds `refactor.map-conflict` naming that site and both entries, the exit code is 1
  and nothing changes

#### Scenario: Package and module inside it
- **WHEN** a map renames package `pkg/sql/` to `db` by `{module: pkg/sql/__init__.py}` and module
  `pkg/sql/client.py` to `cli`, in either order, and runs with `--apply`
- **THEN** stdout holds a `rename from pkg/sql`/`rename to pkg/db` pair and a `rename from pkg/sql/client.py`/`rename
  to pkg/sql/cli.py` pair, the module ends at `pkg/db/cli.py`, `import pkg.sql.client` becomes `import pkg.db.cli`,
  and the exit code is 0

#### Scenario: Three nested moves
- **WHEN** a map renames packages `pkg/` to `app`, `pkg/sql/` to `db` and module `pkg/sql/client.py` to `cli`
- **THEN** the module ends at `app/db/cli.py` and `from pkg.sql import client` becomes `from app.db import cli`

#### Scenario: Two module entries ending at one path
- **WHEN** a map renames package `pkg/a/` to `c` and module `pkg/b.py` to `c`, where no `c` exists yet
- **THEN** the map is refused with `refactor.name-conflict` and nothing changes

#### Scenario: A module meeting a binding another entry introduces
- **WHEN** a map renames module `pkg/a.py` to `b` and `pkg/__init__.py`'s function `x` to `b`
- **THEN** the map is refused with `refactor.name-conflict` naming `pkg/__init__.py` and nothing changes

#### Scenario: A chain of module names
- **WHEN** a map renames module `pkg/a.py` to `b` and module `pkg/b.py` to `c`, or module `src/a.ts` to `b` and module
  `src/b.ts` to `c`
- **THEN** stderr is `[resolve]`, `[checks]` and `refactor.name-conflict` naming `pkg/b.py` or `src/b.ts` line 1, the
  exit code is 1 and nothing changes

#### Scenario: Stubs for every moved module file
- **WHEN** a map renames modules `pkg/a.py` to `b` and `pkg/c.py` to `d` and function `pkg/e.py`'s `f` to `g`, with
  `--stub 2.0` and a configured stub
- **THEN** `pkg/a.py` and `pkg/c.py` hold the stub with their own old and new dotted names, and the exit code is 0

#### Scenario: Stub refused for a map holding a package or alias rename
- **WHEN** a map with `--stub 2.0` renames module `pkg/a.py` and either package `pkg/sql/` or the alias `np` of
  `import numpy as np`
- **THEN** stderr is `[resolve]`, `[checks]` and `refactor.stub-not-module`, the exit code is 2 and nothing changes

#### Scenario: Invalid module entries
- **WHEN** entry 1 holds `module` and `symbol`, entry 2 `module` and `retarget`, and entry 3 `module` and `file`
- **THEN** stderr is `refactor.map-invalid` naming entries 1, 2 and 3, through either invoking twin, and the exit code
  is 2

#### Scenario: Module rename equals its map
- **WHEN** `rename --file F --new-name N` and the map `[{module: F, new_name: N}]` run on the same project, for every
  module-rename case of the corpus in either language
- **THEN** their stdout, stderr and exit codes are identical

### Requirement: Cheap checks run before any reference search
Resolving every entry's locator SHALL search no references. Every resolution failure SHALL be collected with its entry
index, not stop the run: unresolved or ambiguous symbol paths, an out-of-range line, column or offset, a location that
cannot be renamed, a module rename's new name that cannot name a module (Python: no identifier, or a keyword;
TypeScript: as the TypeScript module-rename requirement defines) as `refactor.cannot-rename`, a retarget out of scope,
a literal value that cannot be written, a TypeScript file outside every project. Duplicate entries SHALL be found among
the resolved entries only.

The `checks` phase SHALL then run, before any reference search:
- every `--keep`, `--with` and `--without` SHALL name an existing file or directory under the project, and a `:LINE`
  a line of an existing file, else `refactor.site-missing` naming the option and the site;
- every line keep (`--keep PATH:LINE`) SHALL name a line, in a file the run can edit (a source of its language, and
  with `--docs` a prose file), whose text holds an entry's old name or a retarget entry's target name, either as
  written (with identifier escapes decoded, and NFKC-normalized for Python) or in the value of a string literal
  starting on that line; or lie in a file the refactor moves; else `refactor.keep-unmatched`. Without `--docs`, a
  spelling inside a comment SHALL NOT count, except in a Python type comment (a comment whose text after `#` and
  optional whitespace starts with `type:`). When an entry that did not resolve spells no name in its locator, or an
  entry renames a `Literal` member, this check SHALL be skipped. A whole-file or directory keep SHALL get no check
  here beyond the site check;
- when every entry is a module rename, each `--with` and `--without` site SHALL be refused with
  `refactor.not-stand-in`;
- `--stub` SHALL be checked as the Python module-rename requirement defines, and refused in a TypeScript run as the
  TypeScript module-rename requirement defines;
- each module rename whose new name is already taken in the code before the refactor (Python: its package binds it, as
  the Python module-rename requirement defines; TypeScript: as the TypeScript module-rename requirement defines) SHALL
  be refused with `refactor.name-conflict`, exit 1;
- Python: for a move, every candidate file (a Python source whose text holds the moved name or module's name) SHALL be
  walked as `dr-compliance --select rope-walk` walks it, and each gap reported as `refactor.rope-walk`;
- Python: the language server SHALL start for `rename`, `retarget` and `rename-map` unless every entry is a module
  rename, or its occurrence index is cached and no entry renames a `Literal` member, and when the baseline phase will run, the configured checker SHALL run once on one source of the refactor; a failure SHALL be reported with its
  cause;
- in both twins, when the refactor's language has its baseline file at the repo root, the repo config SHALL be
  readable and valid, else its error SHALL be reported as the config loader words it, exit 2.

Each `--keep`, `--with` and `--without` argument SHALL get at most one finding; a failure in `checks` SHALL replace its
later exact check. When `resolve` or `checks` found anything, the run SHALL print nothing on stdout, print every
finding on stderr (resolution findings by entry index, site findings in command-line order, the `--stub` finding,
module name conflicts by entry index, walker gaps by path, then checker findings), print no `[references]` line, write
nothing, and exit with the highest exit code of its findings.

#### Scenario: Missing keep path
- **WHEN** a rename passes `--keep src/gone.py`
- **THEN** stderr is `[resolve]`, `[checks]` and `refactor.site-missing` naming `--keep src/gone.py`, the exit code is
  2 and no file changes

#### Scenario: Keep line past the end
- **WHEN** `--keep src/a.py:99` names a line past the end of a 20-line file
- **THEN** stderr ends with `refactor.site-missing` naming `--keep src/a.py:99` and the exit code is 2

#### Scenario: Keep holding no old name
- **WHEN** `--keep architecture` names a directory whose files never spell the renamed name
- **THEN** the checks pass, `refactor.keep-unneeded` naming it is printed at site resolution and the exit code is 0

#### Scenario: Every bad keep at once
- **WHEN** a rename passes three keeps, one missing and two line keeps whose lines hold no old name
- **THEN** stderr lists all three findings in command-line order and the exit code is 2

#### Scenario: Comment-only line keep without --docs
- **WHEN** `--keep src/a.py:9` names a line whose only spelling of the old name is in a comment (a trailing comment
  or a line of a multi-line comment), without `--docs`
- **THEN** stderr ends with `refactor.keep-unmatched` naming `src/a.py:9`, no `[references]` line is printed and the
  exit code is 2

#### Scenario: Comment-only line keep with --docs
- **WHEN** the same keep runs with `--docs` and `--apply`, and the rename's `--docs` pass rewrites mentions of the old
  name in comments
- **THEN** the checks pass, every other mention is rewritten, line 9 is unchanged and the exit code is 0

#### Scenario: Python type comment counts as code
- **WHEN** `--keep src/a.py:4` names a line whose only spelling of the old name is in `# type: Old`, without `--docs`
- **THEN** the check passes and the run goes on to `references`

#### Scenario: Missing classification site
- **WHEN** a member rename passes `--with src/gone.py:3` and `--without src/a.py:400`
- **THEN** stderr lists `refactor.site-missing` for both, no `[references]` line is printed and the exit code is 2

#### Scenario: Unresolved entries listed together
- **WHEN** map entries 2 and 4 name symbols their files do not declare
- **THEN** stderr lists `refactor.symbol-unresolved` for entry 2 and then for entry 4, and the exit code is 2

#### Scenario: Taken module name before any search
- **WHEN** a map renames function `f` and module `pkg/a.py` to `b`, where `pkg/b.py` exists; or function `f` and module
  `src/a.ts` to `b`, where `src/b.ts` exists
- **THEN** stderr is `[resolve]`, `[checks]` and `refactor.name-conflict` naming `pkg/b.py` or `src/b.ts` line 1, no
  `[references]` line is printed, the exit code is 1 and nothing changes

#### Scenario: Invalid module new name before any search
- **WHEN** `rename --file pkg/a.py --new-name a/b` or `rename --file src/a.ts --new-name a/b` runs
- **THEN** stderr is `[resolve]`, `[checks]` and `refactor.cannot-rename`, no `[references]` line is printed, the exit
  code is 1 and nothing changes

#### Scenario: Unresolved entry and bad keep
- **WHEN** entry 1 does not resolve and `--keep src/gone.py` is passed
- **THEN** stderr lists the entry's finding and then `refactor.site-missing`, and the exit code is 2

#### Scenario: Keep matched by an escaped spelling
- **WHEN** `--keep src/a.py:7` names a line whose only spelling of the old name is an escaped string literal
- **THEN** the check passes and the run goes on to `references`

#### Scenario: Keep on a retarget's import line
- **WHEN** a TypeScript retarget passes `--keep` on an import of the target that the retarget removes as a duplicate
- **THEN** the check passes and the import line is unchanged

#### Scenario: Keep of a prose file needs --docs
- **WHEN** `--keep README.md:3` names a line of a prose file that mentions the old name
- **THEN** the check passes with `--docs`, and without it stderr is `refactor.keep-unmatched` naming it

#### Scenario: Walker gaps listed before any search
- **WHEN** rope's walker cannot cover `pkg/a.py` at line 3 nor `pkg/b.py` at line 8, and both spell the name a
  `move-symbol` moves
- **THEN** stderr lists `refactor.rope-walk` for both files in path order, no `[references]` line is printed, the
  exit code is 1 and no file changes

#### Scenario: Checker that cannot run
- **WHEN** `commands.typecheck.python` names a command that exits 2 with a message on stderr, and the baseline file
  exists
- **THEN** stderr ends with `refactor.baseline-failed` and its cause, no `[references]` line is printed and the exit
  code is 1

#### Scenario: Unreadable config
- **WHEN** a rename runs where the language's baseline file exists and `living-architecture.yaml` is not valid YAML
- **THEN** stderr ends with the config error, no `[references]` line is printed, the exit code is 2 and no file
  changes
