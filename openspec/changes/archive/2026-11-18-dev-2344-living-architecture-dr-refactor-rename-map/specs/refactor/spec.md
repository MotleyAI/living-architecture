## MODIFIED Requirements

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
symbols, with one blind-spot scan for every member entry's old name and each refusal reported once (see the
one-report requirement). A site any entry rewrites SHALL NOT be listed as another entry's leftover. Identical edits SHALL merge;
every site two entries rewrite differently SHALL be refused with `refactor.map-conflict` naming the site and both
entries, exit 1, writing nothing. Name conflicts SHALL be checked once, over all entries' edits together, on the code after the whole map: a
declaration another entry renames away SHALL NOT hold its old name, so a chain or a swap of symbol names (members,
parameters, locals, top-level names) applies, in any entry order, and entries that meet on one name or capture each
other's references are refused. A Python renamed keyword or key meeting its new name in one call or literal SHALL be
judged on the names after every entry's edits. When any site is refused with `refactor.map-conflict`, no
name-conflict check SHALL run. A `--with` stand-in that entries with different new names reach SHALL get each such
entry's rewrite, at its declaration and at every reference through it, so each of those sites is refused with
`refactor.map-conflict`, in both twins. A retarget
entry's rewritten references SHALL resolve to its target, which another entry may rename. A retarget entry whose
target another entry renames SHALL write the target's new name.

Every path the map prints (headers, diffs, findings) SHALL be a path before the map. A module rename's move SHALL be
printed as one `rename from`/`rename to` pair, from its old path to its new name beside it; an edit in a file that a
move moves SHALL be printed at the file's old path and, with `--apply`, written before the move. Moves inside a package
another entry moves SHALL compose: every project file SHALL end at the path its own move and every surviving move of
a package holding it produce, in any entry order, and the moves SHALL be made innermost first. The name-conflict
check SHALL see every surviving move composed, so two moves that end at one path, a moved module meeting a name another entry's edits bind in
its package, and a module's new name capturing a reference another entry rewrites are each refused with
`refactor.name-conflict`. A module entry's new name SHALL still be checked against the code before the map (see the
cheap checks), so a chain of module names is refused.

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
- **THEN** each blind spot is printed once, under its group's `[rules]` line, the final report is one
  `refactor.blindspots` line, the exit code is 1 and nothing changes

#### Scenario: Duplicate entries
- **WHEN** two entries locate the same method with new names `a` and `b`
- **THEN** stderr ends with `refactor.map-duplicate` naming both entry indexes and the exit code is 2

#### Scenario: Conflicting edits
- **WHEN** one entry renames `Base.save` to `store` and another renames `Sub.save`, its override, to `keep`
- **THEN** stderr's final report holds `refactor.map-conflict` naming a shared site and both entries, the exit code is
  1 and nothing changes

#### Scenario: Swap in one scope refused
- **WHEN** a map renames module `pkg/a.py` to `b` and module `pkg/b.py` to `a`
- **THEN** stderr is `[resolve]`, `[checks]` and the `refactor.name-conflict` finding of each entry, the exit
  code is 1 and nothing changes

#### Scenario: Swap of symbol names applies
- **WHEN** a map renames parameter `f(x)` to `y` and `f(y)` to `x` and runs with `--apply`
- **THEN** both renames apply, every read of each parameter follows it, and the exit code is 0

#### Scenario: Chain of member names
- **WHEN** a map renames `Q.metrics` to `legacy_metrics` (TypeScript `legacyMetrics`) and `Q.measures` to `metrics`,
  in either entry order, and runs with `--apply`
- **THEN** both renames apply, a call `q.measures() + q.metrics()` becomes `q.metrics() + q.legacy_metrics()`, and
  the exit code is 0

#### Scenario: Chain and swap of each symbol kind
- **WHEN** maps chain and swap two parameters of one function, two locals of one function and two top-level names
  of one module, in either entry order
- **THEN** each map applies and the exit code is 0

#### Scenario: Chain whose freed declaration is kept
- **WHEN** the member chain runs with `--keep` on the line declaring `Q.metrics`
- **THEN** the checks pass, and the map is refused in `conflicts` with the `refactor.name-conflict` finding of the
  entry renaming `Q.measures`, naming the kept line; nothing changes and the exit code is 1

#### Scenario: Stand-in two entries reach
- **WHEN** a map renames `Table.columns` to `fields` and `Result.columns` to `result_columns`, a third class
  `Other` declares `columns` and a function reads it through `o: Other`, and the map passes `--with` the line of
  `Other.columns`
- **THEN** stderr's final report holds `refactor.map-conflict` naming entries 1 and 2 for the declaration's line and
  for the read's line, through either twin, the exit code is 1 and nothing changes

#### Scenario: Map conflict without a name check
- **WHEN** two entries rewrite one site differently and a third entry's new name would capture a reference
- **THEN** the final report holds the `refactor.map-conflict` finding and no `refactor.name-conflict` finding

#### Scenario: Two entries converging on one name
- **WHEN** a map renames parameter `f(x)` to `z` and `f(y)` to `z`
- **THEN** stderr is `[resolve]`, `[checks]` and the `refactor.name-conflict` finding of entry 2 naming the line of
  `f`, and nothing changes

#### Scenario: Two catch variables taking one name
- **WHEN** a TypeScript map renames the variables of two separate `catch` clauses to `err`
- **THEN** both renames apply and the exit code is 0

#### Scenario: Entries capturing each other's references
- **WHEN** one entry renames a module-level `a` to `z`, another renames a function's local `b` to `z`, and that
  function reads `a`, so that each entry alone is clean
- **THEN** the map is refused in `conflicts` with the `refactor.name-conflict` finding of the later entry, naming the
  line of `a`, and nothing changes

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
the resolved entries only. Each resolution failure SHALL be printed as `refactor.entry-refusal`, naming its
entry and locator (see the one-report requirement).

The `checks` phase SHALL then run, before any reference search:
- every `--keep`, `--with` and `--without` SHALL name, a relative PATH resolved against `--project`, an existing file
  or directory under the project, and a `:LINE`
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
- each `new_name` entry of a symbol other than a module SHALL be checked in the scope that declares it (a member:
  the type declaring it, in TypeScript on its own static or instance side; a parameter or local: its own scope; a
  top-level name: its module), and refused with `refactor.name-conflict`, exit 1, when that scope declares the new
  name and no other entry renames every such declaration to another name (naming the first such declaration), or
  when another entry renames a declaration of that scope to the same new name (the later entry's finding, naming the
  earlier entry's first declaration). This check SHALL refuse only what the name-conflict check over the computed
  edits would refuse: declarations that the language lets share a scope under one name (TypeScript declarations
  that merge or whose meanings are disjoint, overloads) SHALL NOT be refused; a pair SHALL be left to `conflicts`
  when a `--keep` covers the line of either declaration, or when the resolved entries do not decide whether the
  name is freed. Conflicts through inheritance, imports or references SHALL be found in `conflicts`;
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
module and own-scope name conflicts by entry index, walker gaps by path, then checker findings), print no `[references]` line, write
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
- **THEN** stderr lists `refactor.symbol-unresolved` for entry 2 and then for entry 4, each inside
  `refactor.entry-refusal` naming its entry and locator, and the exit code is 2

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

#### Scenario: Entries that cannot be located
- **WHEN** a three-entry map's entry 2 is `{file: pkg/c.py, line: 2, col: 11}` on a keyword and its entry 3 is
  `{file: pkg/c.py, line: 2, col: 5}` on whitespace
- **THEN** stderr is `[resolve]`, `[checks]`, then `refactor.entry-refusal` for `entry 2 (pkg/c.py:2:11)` and for
  `entry 3 (pkg/c.py:2:5)`, each holding `refactor.cannot-rename`, and the exit code is 1

#### Scenario: Collision in the declaring scope found before any search
- **WHEN** a map renames member `Q.measures` to `metrics` where `Q` declares `metrics`, parameter `f(x)` to `y` where
  `f` has a parameter `y`, a local `a` of `g` to `b` where `g` binds `b`, and top-level `one` to `two` where the
  module binds `two`, and no entry renames any of the existing names
- **THEN** stderr is `[resolve]`, `[checks]` and four `refactor.name-conflict` findings, one per entry in entry order,
  each inside `refactor.entry-refusal` and naming the existing declaration's line; no `[references]` line is printed
  and the exit code is 1

#### Scenario: Python member declared through self
- **WHEN** a Python map renames `C.old` to `fresh` where a method of `C` assigns `self.fresh`
- **THEN** the map is refused in `checks` with `refactor.name-conflict` naming the line of that assignment

#### Scenario: Names the language lets share a scope
- **WHEN** a TypeScript map renames interface `A` to `B` where the module declares a function `B` and no type `B`;
  or renames instance method `C.a` to `b` where `C` declares a static `b`; or renames a `let x` of one block to `y`
  where a sibling block declares `y`
- **THEN** the checks pass and each rename applies

#### Scenario: Python scopes that do not collide
- **WHEN** a Python map renames a function's local `a` to `b` where only a nested function, a comprehension in it or
  a class nested in it binds `b` and none of them reads `a`
- **THEN** the checks pass and the rename applies

#### Scenario: Kept declaration left to the conflicts phase
- **WHEN** a map renames `Q.measures` to `metrics` where `Q` declares `metrics`, with `--keep` on the line declaring
  `Q.measures`
- **THEN** stderr holds a `[references]` line: the `checks` phase refuses nothing for that pair

#### Scenario: Sites from outside the project
- **WHEN** `dr-refactor --project proj rename-map ...` runs from the directory holding `proj` with
  `--keep pkg/a.py:7`, `--with pkg/b.py:5` or `--without pkg/b.py:5`, each a path under `proj`
- **THEN** each site is found; the same run with `--keep proj/pkg/a.py:7` prints `refactor.site-missing`, exit 2

### Requirement: Refactors run in announced phases and report their progress
Every `dr-refactor` subcommand SHALL run in the phases `resolve`, `checks`, `references`, `rules`, `conflicts`,
`baseline` and `write`, in that order, and SHALL print `refactor.progress-phase` on stderr when each phase starts. A
phase that does not run SHALL print nothing: `rules` runs for `rename`, `retarget` and `rename-map` unless every
entry is a module rename; `conflicts` runs for `rename`, `retarget` and `rename-map` when the run reaches the checks
made over its computed edits (the sites two entries rewrite differently and every name-conflict check), so not after a
`--fail-fast` stop and not after a refusing finding at site resolution; `baseline` runs when the refactor's language has its baseline file at the repo root and, for Python,
its `commands.typecheck` entry is set, whether or not anything is then realigned; `write` runs only with `--apply`.

Site resolution SHALL run once every entry's edits are final (every group's rules done, the imports retargets need
planned and every keep applied to the edits and the moves) and before
`conflicts`. It prints no phase line; its `refactor.keep-unneeded` lines SHALL be printed there, in command-line
order.

In `references`, `refactor.progress-item` SHALL be printed for each entry when its reference search starts, in map
order, an entry merged with a duplicate counting once: `n` its position, `count` the number of entries after
merging, `entries` every map index it stands for (`refactor.progress-entry` for one, `refactor.progress-entries` for
several), `new` its new name (a retarget's target name); a module rename's entry SHALL print its line like any other.
`move-symbol` and `move-module` print no per-entry lines.

In `rules`, the entries other than module renames SHALL be taken in groups of one old name, in the order of each
group's first entry. When a
group is done, its line SHALL be printed: `refactor.progress-clean` when it has no refusal of its own, else
`refactor.progress-refused` with the number of its refusals, followed by those refusal lines in path, line and column
order; a refusal printed there SHALL NOT be printed again. `count` SHALL be the number of groups, `entries` the group's map indexes and `new` its distinct new names in
map order, comma-separated. A group's refusals SHALL be counted after its sites under `--keep` are dropped. Refusals
between entries (map conflicts, name conflicts over the merged edits, site findings) SHALL appear only in the final
report.

`conflicts` SHALL print its phase line and no per-entry line.

Progress lines SHALL pass through forwarding to the other twin unchanged and in order.

#### Scenario: Phases of a clean map
- **WHEN** `dr-refactor rename-map map.yaml` runs a two-entry map that refuses nothing, without `--apply`, in a repo
  without a baseline file
- **THEN** stderr is `[resolve]`, `[checks]`, `[references]`, one `[references n/2]` line per entry, `[rules]`, one
  `clean` line per old-name group and `[conflicts]`, and stdout is the headers, the diffs and the dry-run footer

#### Scenario: A refused group prints its refusals as it finishes
- **WHEN** a map's second entry meets an untyped receiver and its first does not
- **THEN** the first group's line says `clean`, the second's says `1 refusal(s)` followed by the blind-spot line, and
  the final report is the `refactor.blindspots` line alone, exit code 1

#### Scenario: Unrelated entries sharing an old name
- **WHEN** a map renames two unrelated methods both named `save`, to `store` and `keep`
- **THEN** one `[rules 1/1]` line names `entries 1, 2`, `save -> store, keep`

#### Scenario: Merged duplicate entries
- **WHEN** entries 2 and 5 locate the same symbol with the same new name
- **THEN** one `[references]` line names `entries 2, 5` and `count` is one less than the number of map entries

#### Scenario: Apply phases
- **WHEN** a rename runs with `--apply` in a repo whose Python baseline file exists and checker command is set
- **THEN** stderr holds `[conflicts]`, then `[baseline]` and then `[write]` after `[rules]`

#### Scenario: Name conflict found in its phase
- **WHEN** a rename's new name is already bound where a renamed read resolves
- **THEN** stderr holds `[conflicts]` before the `refactor.name-conflict` finding, and the exit code is 1

#### Scenario: Module rename conflicts
- **WHEN** a Python module rename's edits change what a name means in an importer
- **THEN** stderr is `[resolve]`, `[checks]`, `[references]`, one `[references 1/1]` line, `[conflicts]` and the
  `refactor.name-conflict` finding, with no `[rules]` line

#### Scenario: Map of a module and a symbol
- **WHEN** a map renames a module and a function and refuses nothing
- **THEN** stderr holds one `[references n/2]` line per entry, `[rules]` with one line for the function's group, and
  `[conflicts]`

#### Scenario: No conflict phase after a fail-fast stop
- **WHEN** a map runs with `--fail-fast` and its first group refuses
- **THEN** stderr holds no `[conflicts]` line

#### Scenario: No conflict phase after a refusing site finding
- **WHEN** a map runs without `--fail-fast` and a line keep matches nothing
- **THEN** stderr holds every `[rules]` result line, no `[conflicts]` line and then the final report

#### Scenario: Warnings before the conflict phase
- **WHEN** a map runs with an unneeded file keep and nothing refuses
- **THEN** stderr holds the `[rules]` result lines, then `refactor.keep-unneeded`, then `[conflicts]`

#### Scenario: Move phases
- **WHEN** `move-module` runs without `--apply`
- **THEN** stderr is `[resolve]`, `[checks]`, `[references]` and no per-entry line

#### Scenario: Progress through the other twin
- **WHEN** a TypeScript rename runs through the PyPI twin
- **THEN** stdout, stderr and exit code equal the npm twin's own run

### Requirement: Every refusal of a run is reported in one report
A run SHALL refuse once, with every refusal it found: those of `resolve` and `checks` as one report before any
reference search, else every refusal found while computing the entries. A walker gap the checks did not predict and
an unresolved base SHALL be recorded and the run SHALL go on. Once every entry's edits are final, site resolution
SHALL decide every `--keep`, `--with` and `--without` site exactly (see the `--keep` and stand-in requirements); it
SHALL be skipped after a `--fail-fast` stop and, in the Python twin, when an entry failed while computing. When it
finds a refusing site finding, the run SHALL stop there, before `conflicts`, and report. Otherwise, after
`conflicts`, every site two entries rewrite differently SHALL be reported, or, when there is none, each entry's
first name conflict (each distinct finding once).

Each refusal SHALL be printed once. A group's refusals (its entries' failures while computing, retarget refusals,
blind spots, stand-ins) SHALL be printed under its `[rules]` line only. The final report SHALL hold only what no
`[rules]` line printed: the failures of entries whose group printed no line (a module entry's, or an entry's after
a `--fail-fast` stop before `rules`) by entry index; name conflicts by entry index; map conflicts in path, line
and column order; then the site findings
(`refactor.not-stand-in` for the `--with` and then the `--without` sites, then `refactor.computed-stand-in`, then
the keep findings, each in command-line order); then the `refactor.blindspots` line when blind spots refuse. With
nothing to hold, the final report SHALL print nothing. The run's exit code SHALL be the highest of all its
refusals', wherever they were printed, 2 for an invalid or duplicate map entry (`refactor.map-invalid`,
`refactor.map-duplicate`), a locator or a site finding, and 1 otherwise, `refactor.map-conflict` included. A file
that changed while the run read it, a write that failed, a checker that failed while computing, and a map document
that cannot be read SHALL still stop the run at once.

A refusal of one entry SHALL be printed as `refactor.entry-refusal`: the entry's label (`refactor.progress-entry`, or
`refactor.progress-entries` with every map index merged into it), its locator as the map writes it (`FILE:LINE:COL`,
`FILE:LINE`, `FILE SYMBOL`, `FILE offset N`, or a module entry's path, FILE relative to `--project`), then the
finding. This SHALL hold for every resolution failure, every failure of an entry while computing, and every
`refactor.name-conflict` of `rename`, `retarget` and `rename-map`, whichever check finds it. A name conflict SHALL
belong to the entry whose new name it names; when the renamed declarations of two or more entries meet, to the
latest of them, naming the earliest one's first declaration. Findings that name their entries themselves
(`refactor.map-invalid`, `refactor.map-duplicate`, `refactor.map-conflict`, `refactor.map-module-unsupported`),
a group's other refusals under its `[rules]` line, and findings of the run as a whole (sites, keeps, `--stub`, the
checker, the config, a write) SHALL be printed as they are. `move-symbol` and `move-module` have no entries and
SHALL print their findings as they are.

#### Scenario: Retarget refusal and blind spot together
- **WHEN** a map's retarget entry meets an overriding member and its rename entry meets an untyped receiver
- **THEN** each is printed once, under its group's `[rules]` line, the final report is the `refactor.blindspots`
  line, and the exit code is 1

#### Scenario: Late unmatched keep with other refusals
- **WHEN** `--keep src/a.py:5` names a code line spelling the old name where no edit lands, and an entry meets an
  untyped receiver
- **THEN** stderr holds the blind spot once, under its group's `[rules]` line, no `[conflicts]` line, and a final
  report of the keep finding naming `src/a.py:5` and then the `refactor.blindspots` line; the exit code is 2

#### Scenario: Unneeded keep and unmatched line keep together
- **WHEN** a rename passes an unneeded `--keep src/compat.py` and a line keep `--keep src/a.py:5` that matches nothing
- **THEN** stderr holds `refactor.keep-unneeded` naming `src/compat.py`, then the final report with the line keep's
  finding, no `[conflicts]` line, and the exit code is 2

#### Scenario: Unneeded keep with a blind spot
- **WHEN** a rename passes an unneeded `--keep src/compat.py` and an entry meets an untyped receiver
- **THEN** stderr holds the blind spot under its group's `[rules]` line, then `refactor.keep-unneeded`, then
  `[conflicts]`, then the `refactor.blindspots` line, and the exit code is 1

#### Scenario: Two map conflicts
- **WHEN** two pairs of entries each rewrite one site differently
- **THEN** stderr lists `refactor.map-conflict` for both sites in path order and the exit code is 1

#### Scenario: Stand-in printed once
- **WHEN** a one-entry map renames `A.m` and an unrelated class `B` declares `m`
- **THEN** stderr holds the `refactor.stand-in` line once, under `[rules 1/1]`, then `[conflicts]` and nothing
  after it, and the exit code is 1

#### Scenario: Literal-unresolved printed once
- **WHEN** a `Literal` member rename meets a site the checker needs the old value at
- **THEN** stderr holds that `refactor.literal-unresolved` line once and the exit code is 1

#### Scenario: Entry failing while it is computed
- **WHEN** entries 1 and 2 of a map share an old name and entry 2's new name is a keyword
- **THEN** the group's `[rules]` line is followed by `refactor.entry-refusal` for entry 2 holding
  `refactor.cannot-rename`, printed once, and the exit code is 1

#### Scenario: Name conflict names its entry
- **WHEN** entry 2 of a map renames a module-level `old` to `next` and a function binds a local `next` and reads `old`
- **THEN** stderr ends with `refactor.entry-refusal` for entry 2 and its locator, holding the `refactor.name-conflict`
  finding

#### Scenario: Single rename names entry 1
- **WHEN** `rename --file F --line 2 --col 11 --new-name n` points at a keyword
- **THEN** stderr ends with `refactor.entry-refusal` for `entry 1 (F:2:11)` holding `refactor.cannot-rename`, as the
  one-entry map prints it

### Requirement: --fail-fast stops at the first refusal
`dr-refactor rename`, `retarget` and `rename-map` SHALL accept `--fail-fast`. With it, the run SHALL stop at the first
refusal found after `checks`: the entry or group in progress SHALL finish its phase and print its line, no later one
SHALL start that phase and no later phase SHALL run. The final report SHALL list what was found and not yet printed, without site
resolution (no exact site finding and no `refactor.keep-unneeded`). Without it, every entry SHALL be computed and
every refusal reported, up to a stop at site resolution.

#### Scenario: Stop after the first refused group
- **WHEN** a three-entry map with distinct old names runs with `--fail-fast` and its first entry meets an untyped
  receiver
- **THEN** stderr holds one `[rules 1/3]` refused line followed by that blind spot, printed once, no `[rules 2/3]`
  line, a final report of the `refactor.blindspots` line, and the exit code is 1

#### Scenario: Default computes every entry
- **WHEN** the same map runs without `--fail-fast` and its first and third entries each meet an untyped receiver
- **THEN** stderr holds three `[rules]` result lines, each blind spot once under its own, and a final report of the
  `refactor.blindspots` line

#### Scenario: Stop on a stand-in
- **WHEN** a two-entry map with distinct old names runs with `--fail-fast` and its first entry meets an unclassified
  stand-in
- **THEN** stderr holds the `[rules 1/2]` refused line and the `refactor.stand-in` line once, nothing after it, and
  the exit code is 1

### Requirement: --keep leaves sites untouched
`dr-refactor rename` SHALL accept `--keep PATH[:LINE]` (repeatable). A relative PATH SHALL be resolved against
`--project` to a real path under the project, in every check and use; a directory SHALL match the files under it by whole path components.
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

#### Scenario: Keep relative to the project
- **WHEN** `dr-refactor --project proj rename ... --keep pkg/a.py:7` runs from the directory holding `proj`, where
  line 7 of `proj/pkg/a.py` holds a reference
- **THEN** that line is unchanged, every other reference is renamed and the exit code is 0; an absolute path naming
  the same line keeps it too

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

`--with PATH:LINE` and `--without PATH:LINE` (each repeatable, a relative PATH resolved against `--project`) SHALL
classify every stand-in member declared on that
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
- **THEN** stderr holds, once, the `refactor.stand-in` line naming `_ModelReadCache.get_model` with its path and
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

### Requirement: Renames keep every reference's binding
A `rename`, and every `new_name` entry of a `rename-map`, SHALL be refused when the edits it would write change which
declaration a name resolves to. The check SHALL cover every identifier spelled with the old or the new name, in every
source file of the project, that the language resolves by scope: in TypeScript bare references, declaration names,
import and export specifiers' names (the imported and re-exported names included), shorthand property values and
type references, each resolved with the meaning (value, type or namespace) its position requires; in Python every name read and every binding (`def`,
`class`, parameters, import aliases, `global` and `nonlocal`, `except`, `match`, `for`, `with`, comprehension and
walrus targets, type parameters), names bound by a star import of a project module (its `__all__` when that is a
literal list or tuple, else its module-level names not starting with `_`), and the forward-reference strings the
rename rewrites, each read in its enclosing scope. Edits in comments, docstrings, prose files, string members,
`Literal` values, string dictionary keys and call keywords SHALL NOT take part. After the edits:
- every rewritten occurrence SHALL resolve to the declaration it resolved to before, under its new name;
- every other occurrence SHALL resolve to the declaration it resolved to before, a language builtin or global
  included;
- no renamed declaration SHALL share, under its new name, a scope and a meaning with another declaration;
- an occurrence left by `--keep` MAY resolve to nothing, and SHALL NOT resolve to a declaration other than its own.

The check SHALL judge the code after every entry's edits. A refused rename SHALL print, for each entry it refuses,
the `refactor.name-conflict` finding with that entry's new name and its first site, in the original code, by project-relative path and then character offset, among: an existing declaration of the new name
that a rewritten occurrence or a renamed declaration would meet; an existing occurrence whose declaration would
change; the declaration a kept occurrence would resolve to; and, when renamed declarations of two entries would meet,
the earliest entry's first declaration, as the latest entry's finding. It SHALL write nothing and exit 1. Name conflicts SHALL be checked after
`--keep` is applied and before the blind-spot and stand-in refusal. A rename to the old name SHALL succeed as a rename
with no edits.

#### Scenario: Reference captured by an inner binding
- **WHEN** `old` is renamed to `next` in a module holding `old = 1` (TypeScript `export const old = 1`) and a function
  that binds a local `next` and returns `old + next`
- **THEN** stderr ends with the `refactor.name-conflict` finding naming `next` and the line of the local `next`, the exit
  code is 1 and no file changes

#### Scenario: Name the declaring scope already binds
- **WHEN** a module-level `old` is renamed to `f` and the module defines a function `f`
- **THEN** the rename is refused naming the line of `f`

#### Scenario: Outer reference shadowed by the renamed declaration
- **WHEN** a module binds `nxt = 5` and a function binds a local `old2` and returns `old2 + nxt`, and `old2` is
  renamed to `nxt`
- **THEN** the rename is refused naming the line of the function's read of `nxt`

#### Scenario: Builtin shadowed
- **WHEN** a module-level `old` is renamed to `len` (TypeScript `parseInt`) and a function of the module calls `len`
  (`parseInt`)
- **THEN** the rename is refused naming the line of that call

#### Scenario: Importer already binds the new name
- **WHEN** `old` in `m` is renamed to `next` and another module imports `old` from `m` directly and binds its own
  `next`
- **THEN** the rename is refused naming the line of the importer's `next`

#### Scenario: Re-export boundary in TypeScript
- **WHEN** `src/index.ts` re-exports `old` from `./m`, `src/use.ts` imports `old` from `./index` and binds its own
  `next`, and `old` in `src/m.ts` is renamed to `next` in a project where nothing else captures it
- **THEN** the re-export becomes `export { next as old }`, `src/use.ts` is unchanged and the exit code is 0

#### Scenario: Aliased import in TypeScript
- **WHEN** `src/m.ts` re-exports `./other` (which exports `next`) with `export *` and declares `old`, `src/use.ts`
  imports `next as n` from `./m`, and `old` is renamed to `next`
- **THEN** the rename is refused naming the line of `src/use.ts`'s import

#### Scenario: Re-export and star-import chains
- **WHEN** `old` in `a` reaches a module through two re-exports (Python: two star imports) and that module binds
  `next` and reads `old`
- **THEN** the rename to `next` is refused naming the first site the chain's last module would change

#### Scenario: Type and value meanings in TypeScript
- **WHEN** a constant `old` is renamed to `next` in a module declaring `type next = string`, and the module uses
  `next` only as a type and `old` only as a value
- **THEN** the rename proceeds and exits 0

#### Scenario: Declaration merging in TypeScript
- **WHEN** an interface `Old` is renamed to `Next` in a module declaring a class `Next`
- **THEN** the rename is refused naming the line of the class

#### Scenario: Overloads renamed as one
- **WHEN** a TypeScript function with two overload signatures and its implementation, or a Python function with an
  `@overload` group, is renamed to a free name
- **THEN** every declaration of the group is renamed and the exit code is 0

#### Scenario: Python scope rules
- **WHEN** a method binds a local named like a class-body attribute, a comprehension's first iterable reads an outer
  name, a walrus in a comprehension binds in the enclosing function, and functions declare `global` and `nonlocal`
  names, and renames to and from those names run
- **THEN** each rename is refused exactly when a name read by the code would resolve to another declaration, as
  Python itself resolves it

#### Scenario: Python class body reads before binding
- **WHEN** a class body reads `old` and binds `next` only after the read, and the module-level `old` is renamed to
  `next`
- **THEN** the rename proceeds and exits 0; it is refused when a binding of `next` may run before the read (earlier
  in the body, conditionally or not, or in a loop holding the read)

#### Scenario: Forward-reference string captured
- **WHEN** class `Old` is renamed to `Next` and a function that binds a local `Next` annotates a local with `"Old"`
- **THEN** the rename is refused naming the line of the local `Next`

#### Scenario: Kept site rebinding
- **WHEN** `--keep` leaves a reference to the inner `old` of a function, and an outer `old` exists
- **THEN** the rename is refused naming the line of the outer `old`

#### Scenario: Kept site dangling
- **WHEN** `--keep` leaves a reference to `old` and no other `old` is in reach
- **THEN** the rename proceeds, that reference is unchanged and the exit code is 0

#### Scenario: Kept declaration
- **WHEN** `--keep` leaves the declaration of `old` while its references are rewritten
- **THEN** the rename is refused naming the first rewritten reference

#### Scenario: No false conflict
- **WHEN** the new name is used only as an attribute (`o.next`), as a call keyword, in a comment, or as a local of an
  unrelated function, and a nested function binds its own `next` without reading `old`
- **THEN** the rename proceeds and exits 0

#### Scenario: Docs and literal members keep their own rules
- **WHEN** a rename with `--docs` rewrites a comment mentioning `old` beside a local `next`, and a `Literal` member
  rename writes a value equal to a local's name
- **THEN** neither edit counts as a conflict
