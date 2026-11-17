## MODIFIED Requirements

### Requirement: dr-* inputs are routed by file language
`dr-refactor`, `dr-compliance` and `dr-mock-lint` SHALL route each input file to the twin of its language,
decided by the registry's source extensions. `dr-refactor`'s language SHALL be the language of `--file`
(`rename`, `retarget`, `move-symbol`), of every entry's `file` or `module` (`rename-map`) or of `--module` (`move-module`); a
source of an unregistered extension, a `--dest` of another language, or a `--module` directory whose expansion
holds more than one language, SHALL exit 1 with a finding. For `dr-compliance` and `dr-mock-lint`, an explicit file
of an unregistered extension, or matching the language's `declaration_globs`, SHALL be skipped with a warning on
stderr; a directory SHALL expand only to files of the repo's languages, or of every registered language when the
repo has none, excluding `declaration_globs` and `excluded_dirs`. The other language's files SHALL run in its twin
with the same working directory and the same options. Output SHALL be one block per language in registry id order,
each exactly as that language's twin prints it alone; stderr SHALL be relayed; the exit code SHALL be the maximum.
When the other twin cannot run or fails with exit 2 or a signal, the command SHALL print nothing on stdout, report
the failure as the forwarding rules define, and exit 2.

#### Scenario: Python-only repo directory expansion is unchanged
- **WHEN** `dr-compliance src` runs in a repo whose only repo language is Python and `src` also holds `app.js`
- **THEN** only the `.py` files are checked and stdout equals today's golden

#### Scenario: Mixed explicit files
- **WHEN** `dr-mock-lint tests/test_a.py web/a.test.ts` runs through either twin, both files violating
- **THEN** stdout is the Python block followed by the TypeScript block, identical for both invoking twins, and the exit code is 1

#### Scenario: Declaration file skipped
- **WHEN** `dr-compliance types/api.d.ts` runs
- **THEN** a warning names the skipped file on stderr and the exit code is 0

#### Scenario: Relative paths from a subdirectory
- **WHEN** `dr-refactor --project .. rename --file src/a.ts --symbol foo --new-name bar` runs through the PyPI twin from a subdirectory
- **THEN** the forwarded run resolves every path against the same working directory and the output equals the npm twin's own run

#### Scenario: Cross-language destination
- **WHEN** `dr-refactor move-symbol --file pkg/a.py --symbol foo --dest web/b.ts` runs
- **THEN** it exits 1 with the cross-language finding and changes nothing

#### Scenario: Mixed-language directory refused
- **WHEN** `dr-refactor move-module --module pkg --dest lib` runs and `pkg` holds both `.py` and `.ts` sources
- **THEN** it exits 1 with a mixed-language finding and changes nothing

#### Scenario: TypeScript map through the PyPI twin
- **WHEN** `dr-refactor rename-map map.yaml` runs through the PyPI twin and every entry names a `.ts` file
- **THEN** the output and exit code equal the npm twin's own run

#### Scenario: A module entry routes by its path
- **WHEN** a map holds a symbol entry on `pkg/a.py` and a module entry `{module: web/b.ts, new_name: c}`
- **THEN** stderr is `refactor.map-mixed-languages`, through either invoking twin, and the exit code is 2

#### Scenario: Base comparison in both blocks
- **WHEN** `dr-mock-lint --base main tests/test_a.py web/a.test.ts` runs through either twin
- **THEN** each language's block holds only its new findings, identical for both invoking twins

### Requirement: Python renames include every reference basedpyright resolves
For a Python `rename` of a symbol other than a module, `dr-refactor` SHALL edit every occurrence the run's occurrence
index resolves to a declaration the rename renames: every declaration of the renamed hierarchy by default, only the
located one with `--no-in-hierarchy`; and every name, import or alias occurrence the checker resolves to no declaration
that Python's scoping and import rules over the project's source folders resolve to one of them. These references SHALL
include forward-reference strings (`"X"`,
`Optional["X"]`, `list["X"]`, `"X | None"`), keyword arguments of dataclass and Pydantic fields at calls whose callee
is the owning class, a subclass or a `type[...]` of either, receivers typed by a parameter annotation, an attribute
annotation (`self.x: T` or a class-body `x: T`), a return annotation or inference, `isinstance`-narrowed receivers,
and `super().name(...)` calls. Every edit SHALL replace exactly the old name, located by source character in
the file's text as read; positions SHALL be correct after non-ASCII and astral characters and with CRLF line endings.
Edits SHALL NOT overlap unless identical; identical edits SHALL be merged. When a file changes between its read and
the write, `dr-refactor` SHALL print the `refactor.file-changed` finding naming that file on stderr, write nothing and
exit 1.

A Python module rename SHALL move the module's file, or a package's directory, to the new name and rewrite, in every
project Python source, each spelling of the module in an import: the renamed segment of a dotted `import` (with or
without `as`), the module path of a `from … import` (absolute or relative) and an imported name that is the module
(`from pkg import old`, `from . import old`, with or without `as`); and every name or attribute load that Python's
scoping and import rules resolve to the module through those bindings (`old.X`, `pkg.old.X`, `other.old.X` where
module `other` binds it); and each string of a module's literal `__all__` that the module resolves to the renamed
module (a binding of it, or the package's own submodule). An `as` alias spelled exactly like the module's own name
SHALL be renamed with every use it binds; any other alias and its uses SHALL be left. Every edit SHALL keep each line's
ending and the file's encoding.
With `--stub REMOVAL`, every module file a run's module renames move SHALL get, after the moves, a stub at its old path
holding `refactor.python.moved_module_stub` with `{old}` and `{new}` (its own old and new dotted names) and
`{removal}` replaced, shown as a new file in the diff; a module whose move a keep drops SHALL get none. `--stub` SHALL
be refused in the `checks` phase, with exit 2 and nothing written: with `refactor.stub-unconfigured` when no stub is
configured, and with `refactor.stub-not-module` when the run renames no module, or one of its module renames is not of
a module file (a package, a namespace package or a library module's alias).
A module rename SHALL be refused with the `refactor.name-conflict` finding when its package already binds the new name
in the code before the refactor (a module of that name, naming it at line 1; a package of that name, naming its
`__init__.py`, else its first Python file by path, at line 1; or a binding in the package's `__init__.py`, naming its
line), in the `checks` phase before any reference search, or when its edits would change a binding as the requirement
that renames keep every reference's binding defines, in the `conflicts` phase; either way writing nothing and exiting 1.

basedpyright SHALL be the version the PyPI twin ships, started from la's own environment, run with la's
pyright#11919 patch, reading the project's own configuration and finding the project's interpreter as basedpyright
does. It SHALL run with its working directory outside the project, without the user site, without bytecode
writing and with neither the working directory nor an inherited `PYTHONPATH` on the interpreter's path, so
no target-repo code runs. A language server
that cannot start, is not patched, fails or exits during the refactor SHALL make `dr-refactor` print the
`refactor.pyright-failed` finding on stderr followed by its cause, as "A failed checker's cause is printed" describes,
write nothing and exit 1. With or without `--apply`, the language server SHALL create no file in the project.

#### Scenario: Forward-reference strings follow the class
- **WHEN** class `Rec` is renamed to `Recommendation` in a module holding `def make() -> "Rec":` and
  `def opt(a: Optional["Rec"], b: list["Rec"], c: "Rec | None") -> None: ...`
- **THEN** every `Rec` inside those strings becomes `Recommendation`, with the quotes and the rest of each string
  unchanged

#### Scenario: Field keyword arguments follow the field
- **WHEN** field `Model.columns` of a Pydantic model is renamed to `fields`, `Sub` subclasses `Model`, and other
  modules call `Model(columns=[])`, `Sub(columns=[], extra=1)` and `kind(columns=[])` with `kind: type[Model]`
- **THEN** each `columns=` becomes `fields=`

#### Scenario: Dataclass field keyword arguments
- **WHEN** field `D.size` of a standard-library dataclass is renamed and a module calls `D(size=1)`
- **THEN** the keyword becomes the new name

#### Scenario: Annotated and inferred receivers
- **WHEN** method `A.get_model` is renamed and the project calls it through a parameter `a: A`, an attribute
  `self.s: A`, a class-body attribute `store: A`, the return of `def make() -> A`, a local `x = A()` and an
  `isinstance(o, A)`-narrowed `o`
- **THEN** each of those calls is renamed

#### Scenario: super() call in an override
- **WHEN** `A.sync_model` is renamed and `class B(A)` overrides it with a body calling `super().sync_model(x)`
- **THEN** the override's name and the `super()` call are renamed

#### Scenario: Hierarchy follows the flag
- **WHEN** `A.run` is renamed, `B(A)` overrides `run`, and the project calls `a.run()` with `a: A` and `b.run()` with
  `b: B`
- **THEN** by default both declarations and both calls are renamed; with `--no-in-hierarchy` only `A.run`, `a.run()`
  and `super().run()` calls resolving to `A.run` are renamed, and `B.run` and `b.run()` are unchanged

#### Scenario: Positions after astral characters and CRLF
- **WHEN** a module with CRLF line endings and no final newline holds `s = "😀é"; r: "Rec" = make()` and `Rec` is
  renamed
- **THEN** only the name inside the string changes, and the line endings and the missing final newline are kept

#### Scenario: Undecodable file
- **WHEN** `pkg/a.py`'s `foo` is renamed and `pkg/b.py` starts with `# coding: nosuch` and imports and calls `foo`
- **THEN** `pkg/b.py` is unchanged, stderr lists `refactor.undecodable` for `pkg/b.py`, and the exit code is 0

#### Scenario: Language server failure
- **WHEN** the language server cannot start or exits during the rename, with or without `--apply`
- **THEN** stderr is the `refactor.pyright-failed` finding followed by its cause, the exit code is 1 and every file of
  the project is unchanged

#### Scenario: No target-repo code runs
- **WHEN** the project's root holds a `sitecustomize.py` that writes a marker file when imported, and a rename runs
- **THEN** the marker file does not exist afterwards

#### Scenario: Dry-run leaves the tree unchanged
- **WHEN** a rename that adds basedpyright references runs without `--apply`
- **THEN** every path under the project is byte-identical before and after, and no new path exists

#### Scenario: Module renamed onto an existing module
- **WHEN** module `pkg/a.py` is renamed to `b`, in one project where `pkg/b.py` exists, in another where a package
  `pkg/b/` exists, and in a third where `pkg/__init__.py` binds `b`
- **THEN** each rename is refused with the name-conflict finding naming `pkg/b.py` line 1, `pkg/b/__init__.py` line
  1 and the binding's line respectively, stderr is `[resolve]`, `[checks]` and that finding, and nothing changes

#### Scenario: Module rename capturing an importer's name
- **WHEN** module `pkg/a.py` is renamed to `b`, no module `b` exists, and `pkg/use.py` holds `from pkg import a` and
  binds its own `b`
- **THEN** the rename is refused naming the line of `pkg/use.py`'s `b`

#### Scenario: Relative import of a renamed module
- **WHEN** module `pkg/a.py` is renamed to `b` and `pkg/use.py` holds `from . import a` with no `b` of its own
- **THEN** the import becomes `from . import b` and the exit code is 0

#### Scenario: Alias spelled like the module
- **WHEN** module `pkg/sql/client.py` is renamed to `cli2`, `tests/a.py` holds `import pkg.sql.client as client` and
  `client.X`, and `tests/b.py` holds `from pkg.sql import client as sql_client` and `sql_client.X`
- **THEN** `tests/a.py` becomes `import pkg.sql.cli2 as cli2` and `cli2.X`, and `tests/b.py` becomes
  `from pkg.sql import cli2 as sql_client` with `sql_client.X` unchanged

#### Scenario: Package rename
- **WHEN** package `pkg/sql/` (with an `__init__.py`) is renamed to `db` and modules import `pkg.sql.engine` and
  `from pkg import sql`
- **THEN** the directory moves to `pkg/db/` and every such import and use names `db`

#### Scenario: Moved-module stub
- **WHEN** `pkg/a.py` is renamed to `b` with `--stub 2.0` and the stub is `raise_moved("{old}", "{new}", removal="{removal}")`
- **THEN** `pkg/b.py` holds the module and `pkg/a.py` holds `raise_moved("pkg.a", "pkg.b", removal="2.0")`

#### Scenario: Stub refused
- **WHEN** `--stub` comes with a symbol rename, a package rename, the rename of a library module's alias, or no
  configured stub
- **THEN** stderr is `[resolve]`, `[checks]` and the finding, the exit code is 2 and nothing changes

#### Scenario: Module rename keeps line endings
- **WHEN** a module renamed by a module rename is imported from a file whose lines end in a mix of CRLF and LF
- **THEN** only the module's spelling changes and every line keeps its own ending

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
code is 2. A Python module rename has no stand-ins: when every entry of the run is a module rename, each `--with` and
`--without` site SHALL print `refactor.not-stand-in` in the `checks` phase; otherwise the sites SHALL be classified by
the run's other entries as above.
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

A whole-file keep of a module file a Python module rename moves, or a keep naming the directory of a package it moves,
SHALL drop that move and every edit in that file or under that directory, and SHALL count as matched; a directory keep
SHALL also drop the moves of the modules and packages under it. A module whose own move is kept SHALL still move with a
package another entry moves, under its old name. In a `rename-map`, every keep SHALL be resolved once, over every
entry's final edits and moves.

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

Every locator SHALL be resolved against the code before any entry is computed, so entries name old names. A Python
module entry SHALL rename the module its file is, a package's `__init__.py` naming the package, exactly as `rename
--file` with no locator does; a module entry and an entry located on an import of the same module SHALL resolve to one
symbol. A module rename, by a module entry or by a locator on an import, SHALL be computed beside any other entries. Two
entries resolving to one symbol with the same intent SHALL merge; with different intents they SHALL be refused with
`refactor.map-duplicate` naming both entry indexes, exit 2. Every entry SHALL then be computed on one snapshot of the
project, every rename rule running once over the union of the entries' symbols, with one blind-spot scan for every
member entry's old name and one combined refusal report, sorted as a single rename sorts it. A site any entry
rewrites SHALL NOT be listed as another entry's leftover. Identical edits SHALL merge; every site two entries rewrite
differently SHALL be refused with `refactor.map-conflict` naming the site and both entries, exit 1, writing nothing. Name conflicts SHALL be checked first for each `new_name` entry alone against
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

In the TypeScript twin, a module entry SHALL be refused with `refactor.map-module-unsupported` naming the entry, for
every module entry in index order, before any phase line, with exit 2 and nothing written.

`rename` SHALL behave as a one-entry map with a `new_name`, and `retarget` as a one-entry map with a `retarget`;
their output SHALL equal that map's byte for byte. A Python `rename --file F --new-name N` with no locator SHALL be the
one-entry map `{module: F, new_name: N}`.

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
- **WHEN** a map renames module `pkg/a.py` to `b` and module `pkg/b.py` to `c`
- **THEN** stderr is `[resolve]`, `[checks]` and `refactor.name-conflict` naming `pkg/b.py` line 1, the exit code is 1
  and nothing changes

#### Scenario: Stubs for every moved module file
- **WHEN** a map renames modules `pkg/a.py` to `b` and `pkg/c.py` to `d` and function `pkg/e.py`'s `f` to `g`, with
  `--stub 2.0` and a configured stub
- **THEN** `pkg/a.py` and `pkg/c.py` hold the stub with their own old and new dotted names, and the exit code is 0

#### Scenario: Stub refused for a map holding a package or alias rename
- **WHEN** a map with `--stub 2.0` renames module `pkg/a.py` and either package `pkg/sql/` or the alias `np` of
  `import numpy as np`
- **THEN** stderr is `[resolve]`, `[checks]` and `refactor.stub-not-module`, the exit code is 2 and nothing changes

#### Scenario: TypeScript module entry
- **WHEN** a map holds `{module: web/a.ts, new_name: b}` and `{module: web/c.ts, new_name: d}`
- **THEN** stderr is `refactor.map-module-unsupported` naming entry 1 and then entry 2, through either invoking twin,
  the exit code is 2 and nothing changes

#### Scenario: Invalid module entries
- **WHEN** entry 1 holds `module` and `symbol`, entry 2 `module` and `retarget`, and entry 3 `module` and `file`
- **THEN** stderr is `refactor.map-invalid` naming entries 1, 2 and 3, through either invoking twin, and the exit code
  is 2

#### Scenario: Module rename equals its map
- **WHEN** `rename --file pkg/a.py --new-name b` and the map `[{module: pkg/a.py, new_name: b}]` run on the same project,
  for every module-rename case of the corpus
- **THEN** their stdout, stderr and exit codes are identical

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
order. `count` SHALL be the number of groups, `entries` the group's map indexes and `new` its distinct new names in
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
  the final report lists the blind spot again with the `refactor.blindspots` line, exit code 1

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

### Requirement: Cheap checks run before any reference search
Resolving every entry's locator SHALL search no references. Every resolution failure SHALL be collected with its entry
index, not stop the run: unresolved or ambiguous symbol paths, an out-of-range line, column or offset, a location that
cannot be renamed, a retarget out of scope, a literal value that cannot be written, a TypeScript file outside every
project. Duplicate entries SHALL be found among the resolved entries only.

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
- when every entry is a Python module rename, each `--with` and `--without` site SHALL be refused with
  `refactor.not-stand-in`;
- `--stub` SHALL be checked as the Python module-rename requirement defines;
- each Python module rename whose package already binds its new name in the code before the refactor SHALL be refused
  with `refactor.name-conflict`, exit 1;
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
- **WHEN** a map renames function `f` and module `pkg/a.py` to `b`, where `pkg/b.py` exists
- **THEN** stderr is `[resolve]`, `[checks]` and `refactor.name-conflict` naming `pkg/b.py` line 1, no `[references]`
  line is printed, the exit code is 1 and nothing changes

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

### Requirement: Python refactors resolve every occurrence from one occurrence index
A Python `dr-refactor` `rename`, `rename-map` or `retarget` of symbols other than modules, and Python
`dr-compliance --attr`, SHALL resolve every occurrence of the old names from one occurrence index of the run: for each
occurrence of an old name in the candidate files (the project's Python sources whose text holds an old name, or a
string constant equal to one under any escaped spelling), its kind (name, member access, keyword argument, dict-literal
key, string-member name, dotted patch target, `Literal`-typed string, forward-reference string, `__all__` entry, import
alias or re-export), the declarations the checker resolves it to (aliases followed, every overload) with every
import-alias or re-export binding it passes through on the way, each with the class declaring it and that class's MRO, and for an access or a string-member object whether the checker types its
receiver. la's language server SHALL export the index in a number of requests that does not depend on the number of
entries or occurrences, and SHALL answer no find-all-references request and no per-occurrence position query for it.

rope SHALL play no part in a Python `rename`, `rename-map` or `retarget`, of a symbol or of a module. A name, import or
alias occurrence of an old name that the checker resolves to no declaration SHALL be resolved by Python's scoping
rules and the project's own modules, without importing or running them: one that resolves to a declaration the rename
renames SHALL be renamed; one that resolves to another declaration SHALL be left; one that resolves to nothing (a name
bound nowhere, or bound by an import of a module neither the checker nor the project's source folders hold) SHALL be
left and listed with the `refactor.unresolved-name` finding on stderr, which does not change the exit code. These lines
SHALL be printed with the leftovers, sorted by path, line and column, and a `--keep` covering a line SHALL drop its
line.

The export SHALL run under the same verification as la's pyright#11919 patch: a basedpyright version it is not
verified for, or a hook that does not match the bundle exactly, SHALL make `dr-refactor` print the
`refactor.pyright-failed` finding on stderr, write nothing and exit 1, and `dr-compliance --attr` print
`compliance.pyright-failed` and exit 2. An exported span that does not slice to the old name's spelling in the file as
read SHALL be refused the same way. The language server SHALL start only when the run needs it, and at most once per
run; a run whose every entry is a module rename, `move-symbol` and `move-module` SHALL NOT start it.

#### Scenario: Export cost does not grow with entries
- **WHEN** a `rename-map` of one entry and a `rename-map` of ten entries run over the same project
- **THEN** both send the same number of export requests, neither sends a references, hover or definition request per
  occurrence, and each prints the same diff as the equivalent single renames merged

#### Scenario: Every member occurrence kind
- **WHEN** field `Model.columns` of a Pydantic model is renamed in a project holding a read `m.columns` with
  `m: Model`, a keyword `Model(columns=[])`, a dict key `Model.model_validate({"columns": []})`,
  `getattr(m, "columns")`, `patch.object(Model, "columns")` and `patch("pkg.mod.Model.columns")`
- **THEN** each of them is renamed, and the output is byte-identical to the output before this change

#### Scenario: Every name occurrence kind
- **WHEN** module-level class `Rec` of `pkg/mod.py` is renamed in a project holding a forward reference `x: "Rec"`, an
  `__all__` entry `"Rec"`, `from pkg.mod import Rec as R`, and a package `__init__.py` re-exporting it with
  `from pkg.mod import Rec` that another module imports from the package
- **THEN** every `Rec` among them is renamed while the alias `R` and its uses stay, and the output is byte-identical
  to the output before this change

#### Scenario: Entry located on an import alias
- **WHEN** `pkg/compat.py`'s `from pkg.core import Model as AcmeModel` is retargeted to `Model`, `pkg/use.py` imports
  `AcmeModel` from `pkg.compat`, and `pkg/other.py` declares its own `from pkg.core import Model as AcmeModel`
- **THEN** the import and the use in `pkg/use.py` are retargeted, `pkg/other.py` is unchanged, and
  `refactor-retarget-reexport-form`'s output is byte-identical to the output before this change

#### Scenario: Overloads, super() and Protocol members
- **WHEN** an overloaded method, a method called through `super().name(...)` in an override, and a member of a
  `Protocol` that a class implements by inheritance are each renamed
- **THEN** every overload signature, the `super()` call and the protocol's and implementer's declarations are renamed

#### Scenario: Import the checker cannot resolve
- **WHEN** `pkg/a.py`'s `foo` is renamed and `scripts/use.py` holds `from pkg.a import foo` and `foo()`, while the
  project's checker configuration does not put the project root on its search path, so basedpyright resolves neither
- **THEN** both occurrences in `scripts/use.py` are renamed, as Python's import rules over the project's source
  folders resolve them

#### Scenario: Name nothing resolves
- **WHEN** `lib/a.py`'s `foo` is renamed and `scripts/use.py` holds `from acme.a import foo` and `foo()`, where no
  source folder of the project holds `acme` and the checker resolves neither
- **THEN** both lines of `scripts/use.py` are unchanged, stderr lists `refactor.unresolved-name` for line 1 and for
  the line of the call after the diff, and the exit code is 0

#### Scenario: Unresolved name kept
- **WHEN** the same rename passes `--keep scripts/use.py`
- **THEN** no `refactor.unresolved-name` line is printed for `scripts/use.py`

#### Scenario: A resolved local is not listed
- **WHEN** `pkg/a.py`'s module-level `foo` is renamed and another function binds its own local `foo` and reads it
- **THEN** the local and its read are unchanged and no `refactor.unresolved-name` line names them

#### Scenario: Unverified checker
- **WHEN** a rename runs with a bundled basedpyright version the export is not verified for
- **THEN** stderr is the `refactor.pyright-failed` finding followed by its cause, the exit code is 1 and every file of
  the project is unchanged

#### Scenario: Positions after astral characters and CRLF in every kind
- **WHEN** each occurrence kind of "Every member occurrence kind" and "Every name occurrence kind" sits in a module with CRLF line endings, a lone `\r`, and
  astral characters before it on its line
- **THEN** exactly the old name is replaced at each, and the line endings are kept

#### Scenario: No server for a module move
- **WHEN** `move-module` or a module rename runs
- **THEN** no language server starts
