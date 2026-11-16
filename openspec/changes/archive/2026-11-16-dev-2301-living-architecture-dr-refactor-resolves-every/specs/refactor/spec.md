## ADDED Requirements

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
rope SHALL NOT search for occurrences: it SHALL locate and validate each entry, rename modules, compute moves, and
resolve, in one batch per run, only the name, import and alias occurrences of an old name that the checker resolves to
no declaration.

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
- **THEN** both occurrences in `scripts/use.py` are renamed, as rope resolves them

#### Scenario: Unverified checker
- **WHEN** a rename runs with a bundled basedpyright version the export is not verified for
- **THEN** stderr is the `refactor.pyright-failed` finding, the exit code is 1 and every file of the project is
  unchanged

#### Scenario: Positions after astral characters and CRLF in every kind
- **WHEN** each occurrence kind of "Every member occurrence kind" and "Every name occurrence kind" sits in a module with CRLF line endings, a lone `\r`, and
  astral characters before it on its line
- **THEN** exactly the old name is replaced at each, and the line endings are kept

#### Scenario: No server for a module move
- **WHEN** `move-module` or a module rename runs
- **THEN** no language server starts

### Requirement: The Python occurrence index is cached between runs
`dr-refactor` and `dr-compliance --attr` SHALL reuse an earlier run's occurrence index exactly when nothing that can
change it has changed: the content of every project source file and the set of those files, the checker's effective
configuration, the interpreter and its search paths, the installed packages and stubs, the basedpyright and export
versions, and the request (the old names, the candidate files and every queried position). Otherwise they SHALL
export the index anew. The cache SHALL hold one entry per project root, in the directory named by `LA_CACHE_DIR` when
it is set, else in the user's cache directory, and never in the project. A missing, unreadable or corrupt cache SHALL
count as absent. Output SHALL be identical with and without a cache entry.

#### Scenario: Re-run after fixing flags
- **WHEN** a `rename-map` dry run refuses on stand-ins and is re-run with `--without` for each, no file having changed
- **THEN** the second run exports nothing and prints the same output as a run without a cache

#### Scenario: A source edit invalidates
- **WHEN** a project source file changes, a file is added that shadows an import, or a file is deleted between two
  runs
- **THEN** the second run exports the index anew

#### Scenario: Environment change invalidates
- **WHEN** the checker configuration, the interpreter or an installed package changes between two runs
- **THEN** the second run exports the index anew

#### Scenario: Corrupt cache
- **WHEN** the cache entry for the project is truncated or not valid
- **THEN** the run exports the index anew and its output equals a run without a cache

#### Scenario: Nothing written in the project
- **WHEN** a rename runs with and without `--apply`
- **THEN** no cache file exists under the project

### Requirement: Python --unsure include renames unresolved receivers
With `--unsure include`, a Python rename SHALL also rename every access `x.OLD` whose receiver the checker types as
`Unknown`, `Any` or a union holding either, and SHALL print the `refactor.unsure-warning` finding on stdout before the
diff. Blind spots SHALL be reported, refused and let through by `--allow-blindspots` as without it. With the default
`--unsure skip` no such access SHALL be renamed.

#### Scenario: Untyped receiver renamed on request
- **WHEN** method `A.run` is renamed with `--unsure include --allow-blindspots` and a module holds `def f(o): o.run()`
- **THEN** `o.run()` becomes `o.<new>()`, stdout starts with the `refactor.unsure-warning` line, and the blind spot is
  listed on stderr

#### Scenario: Skipped by default
- **WHEN** the same rename runs with `--allow-blindspots` only
- **THEN** `o.run()` is unchanged and the blind spot is listed on stderr

## MODIFIED Requirements

### Requirement: Python refactors walk every source construct
The Python `dr-refactor` SHALL compute every refactor over modules that rope's source walker fully covers among the
modules rope walks: those of a move and of a module rename, the module locating each rename entry, and the modules of
the occurrences rope resolves for a rename. Every syntax node SHALL be walked, except expression contexts, operators,
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

### Requirement: Python renames include every reference basedpyright resolves
For a Python `rename` of a symbol other than a module, `dr-refactor` SHALL edit every occurrence the run's occurrence
index resolves to a declaration the rename renames: every declaration of the renamed hierarchy by default, only the
located one with `--no-in-hierarchy`; and every name, import or alias occurrence the checker resolves to no declaration
that rope resolves to one of them. These references SHALL include forward-reference strings (`"X"`,
`Optional["X"]`, `list["X"]`, `"X | None"`), keyword arguments of dataclass and Pydantic fields at calls whose callee
is the owning class, a subclass or a `type[...]` of either, receivers typed by a parameter annotation, an attribute
annotation (`self.x: T` or a class-body `x: T`), a return annotation or inference, `isinstance`-narrowed receivers,
and `super().name(...)` calls. Every edit SHALL replace exactly the old name, located by source character in
the file's text as read; positions SHALL be correct after non-ASCII and astral characters and with CRLF line endings.
Edits SHALL NOT overlap unless identical; identical edits SHALL be merged. When a file changes between its read and
the write, `dr-refactor` SHALL print the `refactor.file-changed` finding naming that file on stderr, write nothing and
exit 1. A module rename SHALL keep rope's edits, and SHALL be refused with the `refactor.name-conflict` finding when
its package already binds the new name (a module of that name, naming it at line 1; a package of that name, naming its
`__init__.py`, else its first Python file by path, at line 1; or a binding in the package's `__init__.py`, naming its
line) or when rope's edits would change a binding as the requirement that renames keep every reference's binding
defines, writing nothing and exiting 1.

basedpyright SHALL be the version the PyPI twin ships, started from la's own environment, run with la's
pyright#11919 patch, reading the project's own configuration and finding the project's interpreter as basedpyright
does. It SHALL run with its working directory outside the project, without the user site, without bytecode
writing and with neither the working directory nor an inherited `PYTHONPATH` on the interpreter's path, so
no target-repo code runs. A language server
that cannot start, is not patched, fails or exits during the refactor SHALL make `dr-refactor` print the
`refactor.pyright-failed` finding on stderr, write nothing and exit 1; no checker or library message text SHALL be
printed. With or without `--apply`, the language server SHALL create no file in the project.

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

#### Scenario: Language server failure
- **WHEN** the language server cannot start or exits during the rename, with or without `--apply`
- **THEN** stderr is the `refactor.pyright-failed` finding, the exit code is 1 and every file of the project is
  unchanged

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

### Requirement: Python --attr reports Unknown and Any receivers
Python `dr-compliance --attr NAME` SHALL report, as the `attr-blindspot` check, every access `x.NAME` whose receiver
basedpyright types as `Unknown`, `Any`, or a union containing either, and every Python string-member form of the
language registry whose member argument is the plain string literal `NAME` and whose object argument is typed so or
whose callee basedpyright cannot resolve while the call has the form's syntax, with the shared
`compliance.attr-blindspot` finding: `{receiver}` SHALL be the receiver's (or object argument's) source text with
each run of whitespace collapsed to one space, and `{type}` SHALL be `Unknown` or `Any` (`Unknown` when both occur,
and for an unresolved callee). Findings SHALL be one per access or call position, sorted by path, line and column.
The verdict at each position SHALL come from the same occurrence index a rename uses, so a site `--attr NAME`
reports is exactly a blind spot a member rename of `NAME` reports there.
basedpyright SHALL start only when `--attr` is given, with the working directory as its workspace, under the same
conditions as for `dr-refactor`. A language server that cannot start, is not patched, fails or exits SHALL make the
command print the `compliance.pyright-failed` finding on stderr and exit 2. The TypeScript twin's `--attr` output
SHALL use the same template with `{type}` `any`.

#### Scenario: Receivers the checker cannot type
- **WHEN** `--attr formula` runs on a file holding `def f(*, measures: list): return [m.formula for m in measures]`,
  `mdl = untyped_call(); mdl.formula`, `hops = []` followed by `map(lambda h: h.formula, hops)`, and
  `def g(o: Any): return o.formula`
- **THEN** each access is reported, the `Any` parameter's with `{type}` `Any` and the others with `Unknown`, and the
  exit code is 1

#### Scenario: Typed receivers are clean
- **WHEN** every receiver of `.formula` in the file is typed with a class declaring `formula`
- **THEN** nothing is reported and the exit code is 0

#### Scenario: Partially unknown union and multiline receiver
- **WHEN** a receiver is typed `Model | Unknown`, and another receiver spans two lines inside parentheses
- **THEN** both are reported, the second with its whitespace collapsed

#### Scenario: String-member forms on untyped objects
- **WHEN** `--attr formula` runs on a file holding `def t(m): getattr(m, "formula")` and
  `def u(monkeypatch): monkeypatch.setattr(obj, "formula", 1)` with `obj: Model`
- **THEN** the `getattr` call is reported with receiver `m` and the `monkeypatch.setattr` call (unresolved callee)
  with receiver `obj` and `{type}` `Unknown`

#### Scenario: Same verdict as a rename
- **WHEN** `--attr formula` and a dry-run rename of member `Model.formula` run on the same project
- **THEN** the positions `--attr` reports are exactly the rename's blind-spot positions

#### Scenario: Language server failure
- **WHEN** `--attr` runs and the language server cannot start
- **THEN** stderr is the `compliance.pyright-failed` finding and the exit code is 2

#### Scenario: TypeScript output unchanged
- **WHEN** `--attr id` runs on a TypeScript file with `function g(o: any) { return o.id }`
- **THEN** stdout is byte-identical to the golden before this change

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
rename SHALL print `refactor.not-stand-in` on stderr in the final report, write nothing and exit 2.
A TypeScript stand-in member declared by a computed name SHALL be classified by `--without` like any other;
`--with` naming its line SHALL print `refactor.computed-stand-in` on stderr, write nothing and exit 2.

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
- **THEN** stderr's final report holds `refactor.not-stand-in` naming that site, the exit code is 2 and no file changes

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
  prints `refactor.computed-stand-in`, writes nothing and exits 2

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
- Python: every module rope walks before the reference search SHALL be walked as `dr-compliance --select rope-walk`
  walks it, and each gap reported as `refactor.rope-walk`: for a move or a module rename every candidate file (a Python
  source whose text holds the moved name or module's name), for any other entry the module locating it;
- Python: the language server SHALL start for `rename`, `retarget` and `rename-map` unless an entry renames a module,
  or the run's occurrence index is cached and no entry renames a `Literal` member, and when the baseline phase will run, the configured checker SHALL run once on one source of the refactor; a failure SHALL be reported with its
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
- **WHEN** rope's walker cannot cover `pkg/a.py` at line 3 nor `pkg/b.py` at line 8, and each is the module locating
  an entry of the map
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
When rope's walker fails on a module while the Python `dr-refactor` computes a refactor, or leaves part of it
uncovered, `dr-refactor` SHALL refuse with the `refactor.rope-walk` finding on stderr, naming the file and the line
of the construct, and exit 1. Every gap in a module rope walks before the reference search SHALL be found in the `checks` phase, before any reference
search, and all of them reported together; a gap met later SHALL refuse the entry that met it while the run goes on.
It SHALL write no file, with or without `--apply`, and print no rope or library message text. The line SHALL be:
- the start line of the first uncovered syntax node or string literal in source order;
- else the start line of the first top-level statement the walker cannot cover on its own;
- else 1.

A gap that does not crash SHALL be refused like one that does. Any other failure SHALL NOT be reported as a
walker gap.

#### Scenario: Gap reported at the construct, not at the drift
- **WHEN** the walker leaves a parameter annotation on line 3 uncovered and its token search fails on line 9
- **THEN** stderr ends with `refactor.rope-walk` naming the module and line 3, the exit code is 1 and no file changes

#### Scenario: Apply writes nothing on a gap
- **WHEN** `dr-refactor --apply rename …` hits a walker gap in any module it analyses
- **THEN** it exits 1 with `refactor.rope-walk` and every file of the project is unchanged

#### Scenario: Silent gap refused
- **WHEN** the walker finishes a module without error but leaves a string literal's tail uncovered
- **THEN** `dr-refactor` exits 1 with `refactor.rope-walk` naming that literal's line
