## ADDED Requirements

### Requirement: Member renames refuse on untyped receivers
A member rename SHALL be a `dr-refactor rename` whose symbol is declared in a class body: in Python a method (sync
or async), property, class attribute, instance attribute (`self.x`) or field; in TypeScript a property, method or
accessor of a class, interface or type literal. A blind spot of the old name OLD SHALL be, in a source file of the
rename's language under the project:
- an attribute access `x.OLD` whose receiver the checker types as unknown (Python `Unknown`, `Any` or a union
  holding either; TypeScript `any`);
- a string-member form whose object argument is typed so, or whose callee the checker cannot resolve while the call
  has the form's syntax (the form's attribute path and the member argument a plain string literal exactly OLD);
- a Python dotted patch target whose first segment names a project top-level package, one of whose segments is
  OLD, and that does not resolve statically to exactly one declaration.

Before writing or printing a diff, a member rename SHALL find every blind spot outside a `--keep` site. With any,
it SHALL print one line per site on stderr, sorted by path, line and column (`compliance.attr-blindspot` for an
access or string form, `refactor.unresolved-target` for a dotted target), then `refactor.blindspots`, print
nothing on stdout, write nothing and exit 1, with or without `--apply`. With `--allow-blindspots` the same lines
SHALL be printed on stderr and the rename SHALL proceed. The set of blind spots SHALL equal what
`dr-compliance --select attr-blindspot --attr OLD <project>` reports, the
project directory expanded as the routing rules expand a directory (Python's `excluded_dirs` naming virtualenv,
version-control and tool-cache directories), plus the unresolved targets and the mixed targets.

#### Scenario: Untyped fixture parameter refuses the rename
- **WHEN** method `Storage.get_model` is renamed and a test function holds `def test_a(storage): storage.get_model("m")`
- **THEN** stderr is the `attr-blindspot` line for `storage.get_model` followed by `refactor.blindspots`, stdout is
  empty, the exit code is 1 and no file changes

#### Scenario: Both refusals under --apply
- **WHEN** a member rename with `--apply` meets one blind spot and one unclassified stand-in
- **THEN** stderr lists the blind spot, then the stand-in, then the closing findings, the exit code is 1 and every
  file of the project is byte-identical

#### Scenario: Override flag proceeds
- **WHEN** the same rename runs with `--allow-blindspots`
- **THEN** the blind-spot lines are printed on stderr, the diff is printed, the untyped call is unchanged and the
  exit code is 0

#### Scenario: Kept blind spot does not block
- **WHEN** the only blind spot is on a line passed to `--keep`
- **THEN** the rename proceeds and exits 0

#### Scenario: Untyped mock fixture callee
- **WHEN** a test holds `def test_b(mocker): mocker.patch.object(engine, "get_model")` with `mocker` unannotated
- **THEN** the call is a blind spot and the rename refuses

#### Scenario: Non-member renames are not scanned
- **WHEN** a module-level function or a parameter is renamed while untyped `x.old` accesses exist
- **THEN** no blind-spot refusal occurs

#### Scenario: TypeScript any receiver
- **WHEN** property `Store.getModel` is renamed in TypeScript and a file holds `function g(o: any) { return o.getModel() }`
- **THEN** the rename refuses with that site's `attr-blindspot` line, `{type}` `any`

#### Scenario: Virtualenv skipped by both
- **WHEN** a Python member rename's project holds `.venv/lib/x.py` with an untyped `o.OLD`
- **THEN** neither the rename nor `dr-compliance --select attr-blindspot --attr OLD <project>` reports it

### Requirement: Member renames refuse on unclassified stand-ins
The renamed hierarchy SHALL be every declaration the rename renames with hierarchy on (Python: rope's hierarchy;
TypeScript: the declarations the language service's rename returns, merged interface declarations included),
whether or not `--no-in-hierarchy` is given, joined with the hierarchy of every `--with` stand-in. A stand-in SHALL
be a class (Python) or a class, interface or type literal (TypeScript), declared in a project source file of the
rename's language and outside the renamed hierarchy, that declares a member named OLD. Object literals SHALL NOT be
stand-ins.

A member rename with any stand-in that is neither `--with` nor `--without` SHALL print one `refactor.stand-in` line
per stand-in member declaration on stderr, sorted by path, line and column and after any blind-spot lines, print
nothing on stdout, write nothing and exit 1, with or without `--apply`.

`--with PATH:LINE` and `--without PATH:LINE` (each repeatable) SHALL classify every stand-in member declared on that
line, together with that stand-in's own hierarchy. A `--with` stand-in SHALL be renamed in the same run: its
hierarchy joins the renamed hierarchy, and every rule of the rename (references, keyed rewrites, string-member
forms, `--docs`, `--keep`, blind spots) SHALL run once over the joined set, on one snapshot of the files, identical
edits merged. A `--without` stand-in SHALL be unchanged. A `--with` or `--without` line holding no stand-in member
declaration of this rename SHALL print `refactor.not-stand-in` on stderr, write nothing and exit 2.
A TypeScript stand-in member declared by a computed name SHALL be classified by `--without` like any other;
`--with` naming its line SHALL print `refactor.computed-stand-in` on stderr, write nothing and exit 2.

#### Scenario: Cast stand-in refuses until classified
- **WHEN** `StorageBackend.get_model` is renamed and `class _ModelReadCache` (no base in the hierarchy) defines
  `get_model` and is used as `cast(StorageBackend, _ModelReadCache(...))`
- **THEN** stderr is the `refactor.stand-in` line naming `_ModelReadCache.get_model` with its path and line, the
  exit code is 1 and no file changes

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
- **WHEN** `--with` names a line that declares no stand-in member of this rename
- **THEN** stderr is `refactor.not-stand-in` naming that site, the exit code is 2 and no file changes

#### Scenario: Two stand-ins on one line
- **WHEN** one line declares two stand-in members named OLD and `--without` names that line
- **THEN** both are classified and neither is reported

#### Scenario: Hierarchy flag off
- **WHEN** `A.run` is renamed with `--no-in-hierarchy` and `B(A)` overrides `run`
- **THEN** `B` is not reported as a stand-in

#### Scenario: TypeScript structural class and object literal
- **WHEN** interface `Store.getModel` is renamed, `class Fake { getModel() {} }` does not implement `Store`, and an
  untyped constant holds `{ getModel() {} }`
- **THEN** `Fake.getModel` is reported as a stand-in and the object literal is not

#### Scenario: Computed-name stand-in
- **WHEN** interface `Store.getModel` is renamed and `class Keyed { [KEY]() {} }` declares it through
  `const KEY = 'getModel'`
- **THEN** `Keyed.getModel` is reported as a stand-in; `--without` its line classifies it, and `--with` its line
  prints `refactor.computed-stand-in`, writes nothing and exits 2

### Requirement: Members named by string are renamed
A rename of a member SHALL rewrite the member argument of each string-member form listed for its language in the
language registry, where the callee resolves to that form, the member argument is a plain string literal whose text
between its quotes is exactly OLD, and the object argument's type is an instance of, a class object or `type[...]`
of, or (TypeScript) the prototype of a class or type whose member lookup (Python's method resolution order;
TypeScript's property lookup) lands on a renamed declaration. The Python forms SHALL be `getattr`, `setattr`,
`hasattr`, `delattr`, pytest's `MonkeyPatch.setattr` and `MonkeyPatch.delattr` with an object first argument,
`unittest.mock`'s `patch.object` and pytest-mock's `patch.object`. The TypeScript forms SHALL be `vi.spyOn`,
`jest.spyOn`, `Reflect.get`, `Reflect.set`, `Reflect.has`, `Reflect.deleteProperty`, `Reflect.defineProperty`,
`Reflect.getOwnPropertyDescriptor`, `Object.defineProperty` and `Object.getOwnPropertyDescriptor`. Only the
characters of OLD SHALL change.
A string-member form whose lookup lands on a renamed declaration and also on a declaration the rename leaves
unchanged (a union of the renamed hierarchy with another class or type) SHALL NOT be rewritten; it SHALL be a blind
spot, printed as `refactor.mixed-target` among the blind-spot lines and counted by `refactor.blindspots`, with
`--keep` and `--allow-blindspots` acting on it as on any blind spot.

A Python rename of a symbol other than a module SHALL also rewrite each segment of the target string of
`unittest.mock`'s `patch`, pytest-mock's `patch`, or `MonkeyPatch.setattr` / `MonkeyPatch.delattr` with a string
first argument, that resolves statically to a renamed declaration: the longest leading run of segments naming a
project module, then each further segment through that module's bindings, imports and re-exports, then class
attributes, without importing or executing project code. A project module SHALL be found under the project's
source folders in order, `a.b` being `<folder>/a/b.py` or `<folder>/a/b/__init__.py` whether or not each directory
has an `__init__.py`; a module found as more than one file SHALL be unresolved. Bindings SHALL follow the rules of
the Python `explicit-any` check: a name resolves only when every module-level binding of it agrees, `from M import
*` binds the names of a literal `__all__` in `M` when it has one, else every name without a leading underscore, and
a cycle ends unresolved. A class attribute SHALL be looked up along the class's method resolution order over its
statically resolved bases; reaching a base that does not resolve before the attribute is found SHALL leave the
target unresolved. A target whose first segment is not a project top-level package and one of whose segments is
OLD SHALL be listed with `refactor.leftover` (`{where}` `patch target`) and leave the exit code unchanged. In a
rename of a symbol other than a member, a project target that does not resolve SHALL be listed the same way.

#### Scenario: Receiver forms on instances and class objects
- **WHEN** `SearchQueryEngine.save_model` is renamed and tests hold `patch.object(SearchQueryEngine, "save_model")`,
  `monkeypatch.setattr(engine, "save_model", fake)` with `engine: SearchQueryEngine` and `monkeypatch:
  pytest.MonkeyPatch`, `mocker.patch.object(engine, "save_model")` with `mocker: MockerFixture`, and
  `getattr(engine, "save_model")`
- **THEN** each `"save_model"` becomes the new name with its quote style kept

#### Scenario: Member of another class
- **WHEN** `getattr(other, "save_model")` has `other: Other` and `Other.save_model` is not renamed
- **THEN** that string is unchanged

#### Scenario: Lookalike callee
- **WHEN** a module defines its own `def getattr(o, n)` and calls `getattr(engine, "save_model")`, and a class
  `Cfg` has a method `setattr(self, o, n)` called as `cfg.setattr(engine, "save_model")` with `cfg: Cfg`
- **THEN** neither string changes and neither is a blind spot

#### Scenario: Dotted patch targets
- **WHEN** `SearchQueryEngine.save_model` is renamed, `pkg/__init__.py` re-exports `SearchQueryEngine` from
  `pkg.engine`, and tests hold `patch("pkg.engine.SearchQueryEngine.save_model")` and
  `patch("pkg.SearchQueryEngine.save_model")`
- **THEN** both targets end in the new name

#### Scenario: Class rename segment
- **WHEN** class `SearchQueryEngine` is renamed to `QueryEngine` and a test holds
  `patch("pkg.engine.SearchQueryEngine.save_model")`
- **THEN** the target becomes `"pkg.engine.QueryEngine.save_model"`

#### Scenario: Unresolved targets
- **WHEN** a test holds `patch("pkg.engine.Missing.save_model")` and `patch("thirdparty.mod.save_model")`
- **THEN** the first is a blind spot (`refactor.unresolved-target`) and the second is listed as a `leftover`

#### Scenario: Unresolved target in a class rename
- **WHEN** class `SearchQueryEngine` is renamed and a test holds `patch("pkg.engine.Missing.SearchQueryEngine")`
- **THEN** the target is unchanged and listed as a `leftover` with `{where}` `patch target`, and the exit code is 0

#### Scenario: Target from tests into a src layout
- **WHEN** `src/pkg/engine.py` declares `SearchQueryEngine.save_model`, `src` is a source folder, and
  `tests/test_t.py` holds `patch("pkg.engine.SearchQueryEngine.save_model")`
- **THEN** the target ends in the new name

#### Scenario: Target through inheritance
- **WHEN** `Base.save_model` is renamed, `Sub(Base)` does not override it, `Over(Base)` does, and tests hold
  `patch("pkg.engine.Sub.save_model")` and `patch("pkg.engine.Over.save_model")`
- **THEN** both targets end in the new name; with `--no-in-hierarchy` only the `Sub` target does

#### Scenario: Ambiguous targets refuse
- **WHEN** `pkg/engine.py` exists in two source folders, or a target passes through a star import that `__all__`
  excludes, an import cycle, or a class whose unresolved base precedes the attribute
- **THEN** each such target is a blind spot (`refactor.unresolved-target`)

#### Scenario: TypeScript spyOn
- **WHEN** method `Engine.saveModel` is renamed and tests hold `vi.spyOn(engine, 'saveModel')` with `engine: Engine`
  and `vi.spyOn(Engine.prototype, 'saveModel')`
- **THEN** both strings become the new name

#### Scenario: Union with an unrenamed class
- **WHEN** `A.saveModel` is renamed in TypeScript, unrelated `B` declaring `saveModel` is passed with `--without`,
  and a file holds `Reflect.get(x, 'saveModel')` with `x: A | B`
- **THEN** stderr holds that site's `refactor.mixed-target` line, the exit code is 1 and no file changes

### Requirement: --keep leaves sites untouched
`dr-refactor rename` SHALL accept `--keep PATH[:LINE]` (repeatable). PATH SHALL be resolved against the working
directory to a real path under the project; a directory SHALL match the files under it by whole path components.
Every edit the rename would make on a kept line, in a kept file or under a kept directory SHALL be dropped,
whichever rule produced it, and a blind spot there SHALL NOT block the rename. A `--keep` that matches no edit and no
blind spot SHALL print `refactor.keep-unmatched` naming it on stderr, write nothing and exit 2. Keeping a
declaration SHALL NOT keep its references.

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

#### Scenario: Unmatched keep
- **WHEN** `--keep src/a.py:99` names a line with nothing this rename touches
- **THEN** stderr is `refactor.keep-unmatched` naming `src/a.py:99`, the exit code is 2 and no file changes

### Requirement: --docs rewrites mentions in comments, docstrings, strings and prose files
`dr-refactor rename --docs` (any symbol other than a module, both languages) SHALL scan the comments and string
literals (Python docstrings and f-string literal parts; TypeScript JSDoc and template-literal text) of every source
file of the rename's language under the project, and the files `config` lists for the project (tracked and
untracked-not-ignored; none outside git) whose extension is among `dr-refactor`'s prose extensions in the shared
contract (`.md`, `.rst`, `.txt`). A mention SHALL be an occurrence of OLD not adjacent to an identifier character.

- A qualified mention SHALL be rewritten in every scanned file: `Owner.OLD`, or `Owner#OLD` in TypeScript, where
  `Owner` names a class of the renamed hierarchy (or, for a module-level symbol, the declaring module's last
  segment), optionally preceded by dotted segments that SHALL form a suffix of the declaring module's dotted path.
  With such a prefix it SHALL be rewritten only when no other project class with that simple name that declares
  OLD sits in a module whose dotted path also ends with those segments; otherwise it SHALL be listed.
  Without such a prefix it SHALL be rewritten only when no other project class with that simple name declares OLD;
  otherwise it SHALL be listed.
- In a declaring file (a source file holding a renamed declaration, `--with` stand-ins included), a code-marked
  bare mention SHALL be rewritten: inside single or double backticks, optionally followed by `()`; the target of a
  Sphinx role or of `{@link OLD}`; or at the start of a string literal followed by `:`, `(` or whitespace.
- Every other mention SHALL be listed: one `refactor.leftover` line per mention on stderr, sorted by path, line and
  column, with `{where}` one of `comment`, `docstring`, `string`, `prose`. Listing SHALL NOT change the exit code.
- Only the characters of OLD SHALL change. A mention another rule already rewrote SHALL NOT be listed.

Without `--docs`, comments, docstrings, prose files and strings other than the forms of the other requirements
SHALL be unchanged and unlisted, with one exception: a member rename SHALL list, as `refactor.leftover` with
`{where}` `string`, each string literal whose whole value is OLD (Python: not a docstring or f-string; TypeScript: a
string literal or a template literal without substitutions) that no other rule rewrote or refused on and that is
not the member or target argument of a string-member form or patch target. Listing SHALL NOT change the exit code.

#### Scenario: Qualified and code-marked mentions
- **WHEN** `SearchQueryEngine.recommend_root_model` is renamed with `--docs`, a docstring elsewhere holds
  ``:meth:`SearchQueryEngine.recommend_root_model` ``, the engine's module holds ``` ``recommend_root_model`` ``` in a
  docstring and `"recommend_root_model: no candidates"` as a message, and `docs/api.md` holds
  `pkg.engine.SearchQueryEngine.recommend_root_model`
- **THEN** all four mentions are rewritten

#### Scenario: Bare words listed
- **WHEN** a comment in another module says `# calls recommend_root_model first` and the engine's module has a
  comment `# then recommend_root_model runs`
- **THEN** neither changes and both are listed as `leftover` with `{where}` `comment`

#### Scenario: Simple-name collision
- **WHEN** another project class also named `SearchQueryEngine` declares `recommend_root_model` and is passed with
  `--without`, and a comment says `SearchQueryEngine.recommend_root_model`
- **THEN** that mention is listed, not rewritten, while `engine.SearchQueryEngine.recommend_root_model` (matching
  the declaring module's path) is rewritten

#### Scenario: Prefix shared by two modules
- **WHEN** `pkg1.engine.SearchQueryEngine.recommend_root_model` is renamed, `pkg2.engine.SearchQueryEngine` also
  declares `recommend_root_model` and is passed with `--without`, and a comment says
  `engine.SearchQueryEngine.recommend_root_model`
- **THEN** that mention is listed, while `pkg1.engine.SearchQueryEngine.recommend_root_model` is rewritten

#### Scenario: Git-ignored prose skipped
- **WHEN** `build/notes.md` is git-ignored and mentions `SearchQueryEngine.recommend_root_model`
- **THEN** it is unchanged and unlisted

#### Scenario: TypeScript JSDoc link
- **WHEN** `Engine.saveModel` is renamed with `--docs` and a JSDoc comment holds `{@link Engine#saveModel}`
- **THEN** the link is rewritten

#### Scenario: Without --docs
- **WHEN** the same rename runs without `--docs`
- **THEN** no comment, docstring, message or prose file changes and nothing is listed

#### Scenario: Exact string literal listed without --docs
- **WHEN** `Storage.get_model` is renamed without `--docs` and a module holds `attrgetter("get_model")` and
  `"get_model is slow"`
- **THEN** both are unchanged, the first is listed as `leftover` with `{where}` `string`, the second is not, and the
  exit code is 0

## MODIFIED Requirements

### Requirement: Compliance check sets are per language
Each language's `dr-compliance` checks SHALL be listed in the language registry. Without `--select`, every
check of each file's language SHALL run. A selected id that no language lists SHALL exit 2; a selected id that
only another language lists SHALL not apply to a file. Python's checks SHALL be `untyped-def`,
`unannotated-attr`, `explicit-any`, `mock`, `rope-walk` and `attr-blindspot`; TypeScript's SHALL be `tsconfig`,
`explicit-any`, `untyped-def`, `mock` and `attr-blindspot`. `attr-blindspot` SHALL run only when selected (or no
`--select` is given) and `--attr NAME` is given. A `--select` naming `attr-blindspot` without `--attr` SHALL print
`compliance.attr-required` on stderr and exit 2; `--attr` with a `--select` that does not name `attr-blindspot`
SHALL print `compliance.attr-unselected` on stderr and exit 2. Every kind a `dr-compliance` finding prints, other
than `parse-error`, SHALL be a registry check id. On files rope's walker fully covers and that reference no `Any`,
Python's output without `--attr` SHALL be unchanged.

#### Scenario: Python default unchanged
- **WHEN** `dr-compliance pkg` runs without `--select` and without `--attr` in a Python repo whose files rope's
  walker fully covers and reference no `Any`
- **THEN** stdout equals today's golden

#### Scenario: Python default reports Any
- **WHEN** `dr-compliance pkg/a.py` runs without `--select` and `pkg/a.py` has `def f(x: Any) -> None`
- **THEN** the `explicit-any` finding for that line is printed and the exit code is 1

#### Scenario: Language-specific id
- **WHEN** `dr-compliance --select tsconfig pkg/a.py` runs
- **THEN** nothing is reported and the exit code is 0

#### Scenario: Python-only id on a TypeScript file
- **WHEN** `dr-compliance --select rope-walk web/a.ts` runs through either twin
- **THEN** nothing is reported and the exit code is 0

#### Scenario: Selecting attr-blindspot
- **WHEN** `dr-compliance --select attr-blindspot --attr formula pkg` runs on files with untyped `def` parameters
  and untyped `.formula` receivers
- **THEN** only `attr-blindspot` lines are printed and the exit code is 1

#### Scenario: attr-blindspot without --attr
- **WHEN** `dr-compliance --select attr-blindspot pkg` runs
- **THEN** stderr is `compliance.attr-required`, stdout is empty and the exit code is 2

#### Scenario: --attr outside the selection
- **WHEN** `dr-compliance --select untyped-def --attr formula pkg` runs
- **THEN** stderr is `compliance.attr-unselected`, stdout is empty and the exit code is 2

### Requirement: TypeScript compliance checks
The TypeScript checks SHALL be: `tsconfig`, one finding per governing tsconfig and per flag whose effective
value after `extends` resolution is not true, among `strict`, `noImplicitAny` and `noImplicitOverride`;
`explicit-any`, every `any` type in the file; `untyped-def`, every parameter, binding element or rest parameter
whose type is implicitly `any` as the type checker determines it with `noImplicitAny` in force (return types
are not required); `mock`, the TypeScript mock-lint rules; and `attr-blindspot`, which with `--attr NAME` SHALL
report `x.NAME` accesses whose receiver's type is `any`, and each TypeScript string-member form of the language
registry whose member argument is the plain string literal `NAME` and whose object argument's type is `any`.
Findings SHALL be sorted per file; a file that does not parse SHALL produce the parse-error finding.

#### Scenario: Strict disables an implied flag
- **WHEN** a tsconfig sets `strict: true` and `noImplicitAny: false`
- **THEN** one `tsconfig` finding names `noImplicitAny` and another names `noImplicitOverride`

#### Scenario: Inherited flags
- **WHEN** a tsconfig extends a base that sets `strict` and `noImplicitOverride`
- **THEN** no `tsconfig` finding is reported

#### Scenario: Contextually typed callback
- **WHEN** a file has `items.map((x) => x.id)` with `items: Item[]` and `function f(a, { b }) {}`
- **THEN** `untyped-def` reports `a` and `b` and not `x`

#### Scenario: Attribute blind spot
- **WHEN** `--attr id` runs on a file with `function g(o: any) { return o.id }`
- **THEN** the access `o.id` is reported

#### Scenario: spyOn on an any object
- **WHEN** `--attr id` runs on a file with `function h(o: any) { vi.spyOn(o, 'id') }`
- **THEN** that call is reported with receiver `o` and `{type}` `any`

### Requirement: TypeScript rename
`rename` SHALL rename every reference the TypeScript language service finds, including overrides and
implementations across the hierarchy, and SHALL keep the shape of shorthand properties and import/export
aliases. Strings and comments SHALL be rewritten only by the string-member forms and by `--docs`, as the other
requirements define. `--no-in-hierarchy` and `--unsure include` SHALL exit 1 with a not-supported finding; the
default `--unsure skip` SHALL be accepted. A symbol that cannot be renamed, such as one declared in a library or
a declaration file, SHALL exit 1 with a stable finding.

#### Scenario: Override renamed with its base
- **WHEN** `Base.run` is renamed and `Child extends Base` overrides `run`
- **THEN** both methods and every call site are renamed

#### Scenario: Shorthand property keeps its key
- **WHEN** a local `foo` used as `{ foo }` is renamed to `bar`
- **THEN** the object becomes `{ foo: bar }`

#### Scenario: Hierarchy flag refused
- **WHEN** `rename --no-in-hierarchy` runs on a TS file
- **THEN** it exits 1 with the not-supported finding and changes nothing

#### Scenario: Library symbol
- **WHEN** the location is a reference to `Array.prototype.map`
- **THEN** it exits 1 with the cannot-rename finding

#### Scenario: Contextually typed object-literal keys
- **WHEN** property `Model.columns` is renamed, `Model.validate(d: Partial<Model>)` is called with
  `{ columns: [] }`, a constant typed `Model` is initialised with `{ columns: [] }`, and an untyped constant holds
  `{ columns: [] }`
- **THEN** the first two keys are renamed and the untyped one is unchanged

#### Scenario: Comments and messages untouched by default
- **WHEN** `Model.columns` is renamed without `--docs` and a comment and a message string mention `columns`
- **THEN** neither changes

### Requirement: Python --attr reports Unknown and Any receivers
Python `dr-compliance --attr NAME` SHALL report, as the `attr-blindspot` check, every access `x.NAME` whose receiver
basedpyright types as `Unknown`, `Any`, or a union containing either, and every Python string-member form of the
language registry whose member argument is the plain string literal `NAME` and whose object argument is typed so or
whose callee basedpyright cannot resolve while the call has the form's syntax, with the shared
`compliance.attr-blindspot` finding: `{receiver}` SHALL be the receiver's (or object argument's) source text with
each run of whitespace collapsed to one space, and `{type}` SHALL be `Unknown` or `Any` (`Unknown` when both occur,
and for an unresolved callee). Findings SHALL be one per access or call position, sorted by path, line and column.
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

#### Scenario: Language server failure
- **WHEN** `--attr` runs and the language server cannot start
- **THEN** stderr is the `compliance.pyright-failed` finding and the exit code is 2

#### Scenario: TypeScript output unchanged
- **WHEN** `--attr id` runs on a TypeScript file with `function g(o: any) { return o.id }`
- **THEN** stdout is byte-identical to the golden before this change
