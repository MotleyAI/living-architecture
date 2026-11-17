## RENAMED Requirements

- FROM: `### Requirement: TypeScript locators`
- TO: `### Requirement: Locators`

## MODIFIED Requirements

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
run; a module rename, `move-symbol` and `move-module` SHALL NOT start it.

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

### Requirement: Python refactors walk every source construct
The Python `dr-refactor` SHALL compute every move over modules that rope's source walker fully covers among the
modules rope walks: those of the move. Every syntax node SHALL be walked, except expression contexts, operators,
`with` items and the internals of f-strings and t-strings. Every string literal SHALL be covered over its full source
text, including every piece of an implicit concatenation and any `r`/`b`/`u`/`f`/`t` prefix in any order and case;
covering surrounding parentheses as well is allowed. This SHALL hold for every construct of the Python versions the
package supports. The following SHALL be refactored like any other code:
- annotations of parameters, `*args`, `**kwargs` and returns, in `def` and `async def`;
- `lambda` parameters of every kind;
- PEP 695 type parameters with bounds and defaults;
- class keywords;
- the `else` of `try/except/else/finally`;
- string literals with `rb`-style prefixes;
- f-strings implicitly concatenated with other literals;
- f-strings and t-strings whose text holds quote characters, triple quotes included;
- Python 3.14 t-strings.

Source positions SHALL be compared in characters, so non-ASCII text anywhere in a module SHALL NOT break a
refactor.

#### Scenario: Annotated parameter with a keyword default inside the annotation
- **WHEN** `dr-refactor rename` runs on a project whose module holds `async def probe(p: Annotated[_Payload | None, Field(description="param text")] = None) -> str:`
- **THEN** it prints the rename's diff and exits 0

#### Scenario: f-string concatenated with a literal holding a parenthesis
- **WHEN** a module of the project holds `c = g(f"{d}" "(")`, or a call whose argument is `"…'QueryFinish' "` followed by `f"AND user = '{u.name}' "` and `"AND query LIKE '%getSetting(%readonly%'"`
- **THEN** a rename in that project prints its diff and exits 0

#### Scenario: f-string holding a triple quote
- **WHEN** a module of the project holds `f"#!/bin/sh\n'''exec' '{sys.executable}' \"$0\" \"$@\"\n' '''\n{body}"`, and another holds `f'{a}"""{b}'`
- **THEN** a rename of a name used in both prints every occurrence and exits 0, and `dr-compliance --select rope-walk` on both modules prints nothing and exits 0

#### Scenario: Class keywords and try-else-finally
- **WHEN** a module holds `class A(B, metaclass=M, x=")"):` and a `try` with `except`, `else` and `finally` blocks whose bodies hold strings with parentheses
- **THEN** a rename of a name used in both prints every occurrence and exits 0

#### Scenario: t-string on Python 3.14
- **WHEN** the twin runs on Python 3.14 and a module holds `f(t"{a}(", ")")`
- **THEN** a rename of `a` prints its diff and exits 0

#### Scenario: Non-ASCII text before an annotation
- **WHEN** a module holds `def f(s: str = "😀", p: A[F(d="(")] = None) -> str: ...`
- **THEN** a rename of `p` prints its diff and exits 0

#### Scenario: A module rope does not walk
- **WHEN** a rename's old name occurs only in modules other than the entry's, each holding a construct rope's walker
  cannot cover, and the checker resolves every occurrence
- **THEN** the rename prints its diff and exits 0 without `refactor.rope-walk`

#### Scenario: A rename walks no module
- **WHEN** a rename's entry module and every module holding its old name hold a construct rope's walker cannot cover
- **THEN** the rename prints its diff and exits 0 without `refactor.rope-walk`

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
module `other` binds it). An `as` alias spelled exactly like the module's own name SHALL be renamed with every use it
binds; any other alias and its uses SHALL be left. Every edit SHALL keep each line's ending and the file's encoding.
With `--stub REMOVAL`, a Python module rename SHALL write, after the move, a stub at the module's old path holding
`refactor.python.moved_module_stub` with `{old}`, `{new}` and `{removal}` replaced, shown as a new file in the diff;
`--stub` on anything but a Python module file, or with no stub configured, SHALL refuse with exit 2 and write nothing.
The module rename SHALL be refused with the `refactor.name-conflict` finding when its package already binds the new name
(a module of that name, naming it at line 1; a package of that name, naming its `__init__.py`, else its first Python
file by path, at line 1; or a binding in the package's `__init__.py`, naming its line) or when its edits would change a
binding as the requirement that renames keep every reference's binding defines, writing nothing and exiting 1.

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
  1 and the binding's line respectively, and nothing changes

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
- **WHEN** `--stub` comes with a symbol rename, a package rename, or no configured stub
- **THEN** it exits 2 with the finding and nothing changes

#### Scenario: Module rename keeps line endings
- **WHEN** a module renamed by a module rename is imported from a file whose lines end in a mix of CRLF and LF
- **THEN** only the module's spelling changes and every line keeps its own ending

### Requirement: Python rename refusals are findings
When an entry's location is not an identifier, names nothing Python's scoping rules or the checker resolve, or its new
name is a Python keyword, the Python `dr-refactor` SHALL report the `refactor.cannot-rename` finding for that entry on
stderr, write nothing and exit 1. No traceback or library message text SHALL be printed.

#### Scenario: Location that is not an identifier
- **WHEN** `rename --offset` points at whitespace between two statements
- **THEN** stderr ends with the `refactor.cannot-rename` finding and the exit code is 1

#### Scenario: Keyword as the new name
- **WHEN** `rename --symbol foo --new-name class` runs
- **THEN** stderr ends with the `refactor.cannot-rename` finding, the exit code is 1 and no file changes

### Requirement: Cheap checks run before any reference search
Resolving every entry's locator SHALL search no references. Every resolution failure SHALL be collected with its entry
index, not stop the run: unresolved or ambiguous symbol paths, an out-of-range line, column or offset, a location that
cannot be renamed, a retarget out of scope, a literal value that cannot be written, a TypeScript file outside every
project. Duplicate entries SHALL be found among the resolved entries only.

The `checks` phase SHALL then run, before any reference search:
- every `--keep`, `--with` and `--without` SHALL name an existing file or directory under the project, and a `:LINE`
  a line of an existing file, else `refactor.site-missing` naming the option and the site;
- every `--keep` SHALL cover at least one line, in a file the run can edit (a source of its language, and with `--docs`
  a prose file), whose text holds an entry's old name or a retarget entry's target name, either as written (with
  identifier escapes decoded, and NFKC-normalized for Python) or in the value of a string literal starting on that
  line; or cover a file the refactor moves; else `refactor.keep-unmatched`. When an entry that did not resolve spells
  no name in its locator, or an entry renames a `Literal` member, this check SHALL be skipped;
- Python: for a move, every candidate file (a Python source whose text holds the moved name or module's name) SHALL be
  walked as `dr-compliance --select rope-walk` walks it, and each gap reported as `refactor.rope-walk`;
- Python: the language server SHALL start for `rename`, `retarget` and `rename-map` unless the run's occurrence index
  is cached and no entry renames a `Literal` member, and when the baseline phase will run, the configured checker SHALL run once on one source of the refactor; a failure SHALL be reported with its
  cause;
- in both twins, when the refactor's language has its baseline file at the repo root, the repo config SHALL be
  readable and valid, else its error SHALL be reported as the config loader words it, exit 2.

Each `--keep`, `--with` and `--without` argument SHALL get at most one finding; a failure in `checks` SHALL replace its
later exact check. When `resolve` or `checks` found anything, the run SHALL print nothing on stdout, print every
finding on stderr (resolution findings by entry index, site findings in command-line order, walker gaps by path, then
checker findings), print no `[references]` line, write nothing, and exit with the highest exit code of its findings.

#### Scenario: Missing keep path
- **WHEN** a rename passes `--keep src/gone.py`
- **THEN** stderr is `[resolve]`, `[checks]` and `refactor.site-missing` naming `--keep src/gone.py`, the exit code is
  2 and no file changes

#### Scenario: Keep line past the end
- **WHEN** `--keep src/a.py:99` names a line past the end of a 20-line file
- **THEN** stderr ends with `refactor.site-missing` naming `--keep src/a.py:99` and the exit code is 2

#### Scenario: Keep holding no old name
- **WHEN** `--keep architecture` names a directory whose files never spell the renamed name
- **THEN** stderr ends with `refactor.keep-unmatched` naming it, no `[references]` line is printed and the exit code
  is 2

#### Scenario: Every bad keep at once
- **WHEN** a rename passes three keeps, one missing and two holding no old name
- **THEN** stderr lists all three findings in command-line order and the exit code is 2

#### Scenario: Missing classification site
- **WHEN** a member rename passes `--with src/gone.py:3` and `--without src/a.py:400`
- **THEN** stderr lists `refactor.site-missing` for both, no `[references]` line is printed and the exit code is 2

#### Scenario: Unresolved entries listed together
- **WHEN** map entries 2 and 4 name symbols their files do not declare
- **THEN** stderr lists `refactor.symbol-unresolved` for entry 2 and then for entry 4, and the exit code is 2

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
- **WHEN** `--keep README.md` names a prose file that mentions the old name
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

### Requirement: A Python walker gap is refused with a located finding
When rope's walker fails on a module while the Python `dr-refactor` computes a move, or leaves part of it uncovered,
`dr-refactor` SHALL refuse with the `refactor.rope-walk` finding on stderr, naming the file and the line of the
construct, and exit 1. Every gap in a module rope walks before the reference search SHALL be found in the `checks`
phase, before any reference search, and all of them reported together; a gap met later SHALL refuse the entry that
met it while the run goes on. It SHALL write no file, with or without
`--apply`, and print no rope or library message text. The line SHALL be:
- the start line of the first uncovered syntax node or string literal in source order;
- else the start line of the first top-level statement the walker cannot cover on its own;
- else 1.

A gap that does not crash SHALL be refused like one that does. Any other failure SHALL NOT be reported as a
walker gap.

#### Scenario: Gap reported at the construct, not at the drift
- **WHEN** the walker leaves a parameter annotation on line 3 uncovered and its token search fails on line 9
- **THEN** stderr ends with `refactor.rope-walk` naming the module and line 3, the exit code is 1 and no file changes

#### Scenario: Apply writes nothing on a gap
- **WHEN** `dr-refactor --apply move-symbol …` hits a walker gap in any module it analyses
- **THEN** it exits 1 with `refactor.rope-walk` and every file of the project is unchanged

#### Scenario: Silent gap refused
- **WHEN** the walker finishes a module without error but leaves a string literal's tail uncovered
- **THEN** `dr-refactor` exits 1 with `refactor.rope-walk` naming that literal's line

### Requirement: Locators
In both twins, `--line` and `--col` SHALL be 1-based and `--offset` 0-based; columns and offsets SHALL count Unicode
code points of the file as read, every line terminator (`\r\n`, `\n`, a lone `\r`) included in an offset, and a column
SHALL count within its line excluding the line terminator. A line, column or offset out of range SHALL exit 1 with a
finding, whose count is the file's code points for an offset. `--symbol` SHALL locate as the symbol-path requirement
defines. No locator SHALL exit 1 with the no-locator finding, except in a Python `rename`, which then renames the module
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

#### Scenario: Offset after CRLF line breaks
- **WHEN** a file with CRLF line endings declares `foo` on its third line and `--offset` counts both characters of each
  earlier line break to reach it
- **THEN** both twins rename `foo`, and an offset one past the file's code points exits 1 with the out-of-range finding
  naming that count
