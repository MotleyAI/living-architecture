## ADDED Requirements

### Requirement: Python field renames rewrite field-name strings
When the renamed symbol is a field of a `pydantic.BaseModel` subclass, the Python `dr-refactor` SHALL rewrite each
plain string literal whose text between its quotes is exactly OLD:
- among the positional arguments of a decorator that resolves to Pydantic's `field_validator` or `field_serializer`
  and decorates a method of a class C, when looking OLD up in C's method resolution order lands on a renamed
  declaration;
- as the subscript of `X.model_fields[...]`, as the first argument of `X.model_fields.get(...)`, and as the left
  operand of `in` or `not in` whose right operand is `X.model_fields` or `X.model_fields_set`, where the attribute
  resolves to Pydantic's and the checker types `X` as an instance of, the class object of or `type[...]` of a class
  whose lookup of OLD lands on a renamed declaration.

Only the characters of OLD SHALL change, and no other argument of the decorator. These strings are field names, so
a field declaring `alias` or `validation_alias`, and a model whose configuration sets an `alias_generator`, SHALL be
rewritten like any other. The forms SHALL be listed in the language registry and matched by the declaration the
callee or attribute resolves to, never by its spelling.

A decorator argument on a class whose lookup finds no declaration of OLD SHALL be unchanged and listed as any other
equal string is. A read form whose lookup lands on a renamed declaration and on one the rename leaves unchanged
SHALL be a `refactor.mixed-target` blind spot; one whose receiver the checker types as `Unknown`, `Any` or a union
holding either SHALL be a `string-blindspot`. A decorator that already holds NEW among its positional arguments
SHALL make `dr-refactor` print `refactor.name-conflict` naming that file and line, write nothing and exit 1.

#### Scenario: Validator on the declaring class
- **WHEN** field `Ds.columns` is renamed to `fields` and `Ds` holds `@field_validator("columns")` on a classmethod
- **THEN** the decorator becomes `@field_validator("fields")` with its quote style kept, and no `leftover` names that
  line

#### Scenario: Validator on a subclass
- **WHEN** `class Sub(Ds)` holds `@field_validator("columns")` and does not redeclare the field
- **THEN** that decorator is rewritten too

#### Scenario: Several names and the wildcard
- **WHEN** `Ds` holds `@field_validator("name", "columns", mode="before")` and `@field_validator("*")`
- **THEN** only `"columns"` in the first decorator changes

#### Scenario: Serializer
- **WHEN** `Ds` holds `@field_serializer("columns")`
- **THEN** the string becomes `"fields"`

#### Scenario: Aliased import and a lookalike
- **WHEN** a module imports `from pydantic import field_validator as fv` and uses `@fv("columns")` on `Ds`, and
  another module defines its own `def field_validator(*names)` and uses `@field_validator("columns")` on a class
  with a `columns` field passed to `--without`
- **THEN** the first string changes and the second does not

#### Scenario: Reads of model_fields
- **WHEN** modules hold `Ds.model_fields["columns"]`, `Ds.model_fields.get("columns")`, `"columns" in
  Ds.model_fields`, `"columns" not in d.model_fields_set` with `d: Ds`, and `type(d).model_fields["columns"]`
- **THEN** every one of those strings becomes `"fields"`

#### Scenario: Another model's fields
- **WHEN** `Other` also has a field `columns`, is passed to `--without`, and a module holds
  `Other.model_fields["columns"]`
- **THEN** that string is unchanged

#### Scenario: Aliased field
- **WHEN** the renamed field is declared `columns: list[str] = Field(alias="cols")` and `Ds` holds
  `@field_validator("columns")` and a module holds `Ds.model_fields["columns"]`
- **THEN** both strings become `"fields"`

#### Scenario: Validator on a base without the field
- **WHEN** a base class without a `columns` field holds `@field_validator("columns", check_fields=False)` and `Ds`
  derives from it
- **THEN** that string is unchanged and listed as a `leftover`

#### Scenario: Union with an unrenamed model
- **WHEN** a module holds `m.model_fields["columns"]` with `m: Ds | Other`
- **THEN** that site is a `refactor.mixed-target` blind spot and the rename refuses

#### Scenario: Decorator already holding the new name
- **WHEN** `Ds` holds `@field_validator("columns", "fields")`
- **THEN** stderr ends with `refactor.name-conflict` naming that line, the exit code is 1 and no file changes

### Requirement: Python attribute renames rewrite class-body name tuples
When the renamed symbol is an attribute, the Python `dr-refactor` SHALL rewrite each plain string literal exactly
OLD in the value assigned to `__slots__` or `__match_args__` in the body of a class C, when looking OLD up in C's
method resolution order lands on a renamed declaration. The value SHALL be a tuple, list or set display whose
element the string is; for `__slots__` also the string itself or a dict display whose key it is. A string anywhere
else in the value (a concatenation, a call) SHALL be unchanged and listed as any other equal string is. A value that
already holds NEW SHALL make `dr-refactor` print `refactor.name-conflict` naming that file and line, write nothing
and exit 1.

#### Scenario: Slots tuple
- **WHEN** attribute `Slotted.columns` is renamed to `fields`, with `__slots__ = ("columns",)` and `self.columns:
  list[str] = []` in `__init__`
- **THEN** the slot becomes `"fields"` and `Slotted()` constructs after the rename

#### Scenario: Other slot shapes
- **WHEN** classes declare `__slots__ = "columns"`, `__slots__ = ["name", "columns"]` and `__slots__ = {"columns":
  "the columns"}` for the renamed attribute
- **THEN** each `"columns"` becomes `"fields"` and no other string changes

#### Scenario: Inherited match args
- **WHEN** `Base.columns` is renamed and `class Sub(Base)` holds `__match_args__ = ("name", "columns")` without
  redeclaring the attribute
- **THEN** that entry becomes `"fields"`

#### Scenario: A class outside the rename
- **WHEN** `Unrelated` declares its own `columns` with `__slots__ = ("columns",)` and is passed to `--without`
- **THEN** its slot is unchanged

#### Scenario: Computed value
- **WHEN** a class holds `__slots__ = Base.__slots__ + ("columns",)`
- **THEN** that string is unchanged and listed as a `leftover`

#### Scenario: Value already holding the new name
- **WHEN** a class holds `__slots__ = ("columns", "fields")`
- **THEN** stderr ends with `refactor.name-conflict` naming that line, the exit code is 1 and no file changes

### Requirement: Python string-member forms name the members of a module
A Python rename of a module-level function, class or variable (not a module) SHALL rewrite the member argument of
each Python string-member form of the language registry whose callee resolves to that form, whose member argument
names OLD, and whose object argument is a name or dotted name that resolves, through its file's bindings and
imports by the rules of dotted patch targets, to exactly one project module M, when the target `M.OLD` resolves by
those rules to a renamed declaration. Only the characters of OLD SHALL change. One whose `M.OLD` resolves to a
declaration the rename leaves unchanged SHALL be unchanged and unlisted. One whose object argument's first segment
is bound to a project top-level package while the object or `M.OLD` does not resolve SHALL be listed with
`refactor.leftover` (`{where}` `patch target`) and leave the exit code unchanged. An object argument that is not a
module SHALL be unchanged, as today. A module rename SHALL NOT rewrite these forms.

#### Scenario: Patch forms on an imported module
- **WHEN** function `list_models` of `pkg/mod.py` is renamed to `list_datasets` and a test holding `from pkg import
  mod` calls `monkeypatch.setattr(mod, "list_models", fake)` with `monkeypatch: pytest.MonkeyPatch` and
  `patch.object(mod, "list_models", return_value=[])`
- **THEN** both strings become `"list_datasets"`, with and without `--docs`

#### Scenario: Module alias and dotted receiver
- **WHEN** tests hold `import pkg.mod as m` with `getattr(m, "list_models")`, and `import pkg.mod` with
  `monkeypatch.setattr(pkg.mod, "list_models", fake)`
- **THEN** both strings change

#### Scenario: Re-exporting package
- **WHEN** `pkg/__init__.py` holds `from pkg.mod import list_models` and a test holds `import pkg` with
  `patch.object(pkg, "list_models")`
- **THEN** that string changes

#### Scenario: Same name in another module
- **WHEN** `pkg/other.py` declares its own `list_models` and a test holds `patch.object(other, "list_models")`
- **THEN** that string is unchanged and unlisted

#### Scenario: Module found twice
- **WHEN** `pkg/mod.py` exists in two source folders and a test holds `patch.object(mod, "list_models")`
- **THEN** that string is unchanged and listed as a `leftover` with `{where}` `patch target`, and the exit code is 0

#### Scenario: Object that is not a module
- **WHEN** a test holds `getattr(engine, "list_models")` with `engine: Engine`
- **THEN** that string is unchanged

### Requirement: A string held by a name is followed to its literal sources
The literal sources of a name SHALL be, in project source files of the rename's language:
- the plain string literal assigned to it, when the name is a local bound exactly once in its function, a
  module-level name bound exactly once, or a class-level name bound exactly once in its class body and read as
  `K.NAME` (Python: a plain or annotated assignment of that one name, not declared `global` or `nonlocal`;
  TypeScript: a `const`, or a `let` assigned exactly once);
- the sources of the name assigned to it under the same conditions, followed through such assignments, imports and
  re-exports;
- for the target of a Python `for` loop or comprehension, or of a TypeScript `for…of` or the first parameter of an
  array-method callback, over a display of plain string literals or over a name bound exactly once to one (Python: a
  tuple, list or set display that no statement mutates; TypeScript: an `as const` array literal), every element of
  that display.

A name bound any other way SHALL have no sources: a parameter, a conditional or computed value, a second binding,
a destructuring or starred target, a walrus target, an augmented assignment, an `except`, `with` or `import`-bound
value, or a literal in a file outside the project's sources (a dependency, a `.pyi` stub, a `.d.ts` file).

A member rename SHALL treat a name in the member position of a string-member form, of a Python field-name read
(`model_fields`, `model_fields_set`), or as the argument of a TypeScript element access `d[s]`, as naming each of
its sources: when the form's object lookup of OLD lands on a renamed declaration, each source literal exactly OLD
SHALL be rewritten, only the characters of OLD changing. When another such use of the same source lands on a
declaration the rename leaves unchanged, nothing of that source SHALL be rewritten and each of its uses SHALL be a
`refactor.mixed-target` blind spot. A use whose object is untyped SHALL NOT be a blind spot. A display that already
holds NEW SHALL make the rename print `refactor.name-conflict` naming that file and line, write nothing and exit 1.
A source literal on a `--keep` line SHALL NOT be rewritten.

A literal-member rename SHALL follow names as its own requirement states.

#### Scenario: Names read from a constant tuple
- **WHEN** attribute `Ds.columns` is renamed to `fields` and a module holds `SECTIONS = ("columns",)` and
  `[getattr(d, s) for s in SECTIONS]` with `d: Ds`
- **THEN** the tuple becomes `("fields",)` and the comprehension is unchanged

#### Scenario: Only the matching element
- **WHEN** the module holds `FIELDS = ("label", "columns")` read by `for f in FIELDS: getattr(d, f)`
- **THEN** only `"columns"` changes

#### Scenario: Direct display and a single constant
- **WHEN** modules hold `for s in ("columns", "name"): setattr(d, s, None)` and `NAME = "columns"` followed by
  `getattr(d, NAME)`
- **THEN** both `"columns"` strings change

#### Scenario: Chain and import
- **WHEN** `pkg/a.py` holds `A = "columns"`, `pkg/b.py` holds `from pkg.a import A` and `B = A`, and a module calls
  `getattr(d, B)`
- **THEN** the literal in `pkg/a.py` changes

#### Scenario: Field-name read through a name
- **WHEN** a module holds `for f in ("columns",): Ds.model_fields[f]`
- **THEN** that element changes

#### Scenario: Use on an unrenamed class
- **WHEN** `SECTIONS = ("columns",)` is read by `getattr(d, s)` with `d: Ds` and by `getattr(o, s)` with `o: Other`,
  `Other.columns` passed to `--without`
- **THEN** both calls print `refactor.mixed-target`, the tuple is unchanged and the rename refuses

#### Scenario: Only an unrenamed class
- **WHEN** the tuple is read only by `getattr(o, s)` with `o: Other`
- **THEN** nothing changes and nothing is reported for it

#### Scenario: Names without sources
- **WHEN** `getattr(d, s)` reads, in separate functions, a parameter `s`, `s` bound in both branches of an `if`,
  `s, t = "columns", "name"`, `(s := "columns")`, `s` iterating a list that the function also appends to, and `s`
  iterating `frozenset({"columns"})`
- **THEN** no string changes and each equal string is listed as a `leftover`

#### Scenario: Display already holding the new name
- **WHEN** the module holds `SECTIONS = ("columns", "fields")` read by `getattr(d, s)`
- **THEN** stderr ends with `refactor.name-conflict` naming that line, the exit code is 1 and no file changes

#### Scenario: Literal member through a module constant
- **WHEN** `Kind2 = Literal["formula", "sql"]` is renamed at `Kind2['formula']` to `expression`, and the module
  holds `DISPATCH_FORMULA = "formula"` and a function returning `Kind2` that returns `DISPATCH_FORMULA`
- **THEN** the constant's literal becomes `"expression"`, the `return` is unchanged and the exit code is 0

#### Scenario: Literal member through a class constant and a loop
- **WHEN** modules hold `class K: FORMULA = "formula"` with `take(K.FORMULA)`, and `for t in ("formula", "sql"):
  take(t)`, for `take(k: Kind2)`
- **THEN** both `"formula"` strings become `"expression"`

#### Scenario: Source in a stub
- **WHEN** the constant passed to `take` is declared `DEFAULT: Final = "formula"` only in a `.pyi` stub outside the
  project's sources
- **THEN** the call site is a `refactor.literal-unresolved` blind spot and the rename refuses with exit 1

#### Scenario: TypeScript constants
- **WHEN** `type Kind2 = 'formula' | 'sql'` is renamed at `Kind2['formula']` to `expression`, and files hold `export
  const DISPATCH_FORMULA = 'formula'` returned from a function typed `Kind2`, `const v = 'formula'` passed to
  `take(k: Kind2)`, and `class K { static readonly FORMULA = 'formula' }` with `take(K.FORMULA)`
- **THEN** each `'formula'` becomes `'expression'` and the exit code is 0

#### Scenario: TypeScript names read from a const array
- **WHEN** property `Ds.columns` is renamed to `fields` and a file holds `const SECTIONS = ['columns'] as const`
  with `SECTIONS.map((s) => d[s])`, `for (const s of SECTIONS) Reflect.get(d, s)` and `d: Ds`
- **THEN** the array becomes `['fields'] as const`

#### Scenario: TypeScript array without as const
- **WHEN** the file holds `const NAMES = ['columns']` read by `for (const s of NAMES) Reflect.get(d, s)`
- **THEN** the array is unchanged and its string is listed as a `leftover`

### Requirement: Unverified reads of a rewritten source are listed
For each source literal a rename rewrites under "A string held by a name is followed to its literal sources", every
read of a name that holds it (the name the literal is assigned to, a name assigned from it, a loop target bound
from it) SHALL print `refactor.unverified-read` on stderr, `{name}` the name read, `{path}` and `{line}` the
read's, `{source_path}` and `{source_line}` the rewritten literal's, unless the read is:
- the assignment, import, re-export or iteration that carries the source to another followed name;
- in a member rename, a use that proves the member (a form whose object lookup lands on a renamed declaration);
- in a literal-member rename, a read the checker needs the renamed literal at.

The lines SHALL be printed with or without `--docs`, sorted by path, line and column, one per read, and SHALL leave
the exit code unchanged. A source that is not rewritten SHALL list nothing.

#### Scenario: Tuple also used as a key
- **WHEN** `Ds.columns` is renamed, `SECTIONS = ("columns",)` sits on line 20 of `pkg/m.py`, a loop over it holds
  `getattr(d, s)` and, on line 31, `doc[s] = 1`
- **THEN** the tuple is rewritten and stderr holds `pkg/m.py:31: unverified-read: s holds 'columns', rewritten at
  pkg/m.py:20; this read is not proven to name the renamed member`, and the exit code is 0

#### Scenario: Second reader of the constant
- **WHEN** another module imports `SECTIONS` and calls `print(SECTIONS)`
- **THEN** that read is listed with `{name}` `SECTIONS`, and the import is not

#### Scenario: Literal constant with an untyped read
- **WHEN** `Kind2['formula']` is renamed, `DISPATCH_FORMULA = "formula"` is returned from a function typed `Kind2`
  and also compared in `doc["kind"] == DISPATCH_FORMULA` with `doc: dict[str, str]`
- **THEN** the constant is rewritten, the comparison is listed and the `return` is not

#### Scenario: Nothing rewritten, nothing listed
- **WHEN** the source's only use lands on an unrenamed class, or the source is on a `--keep` line
- **THEN** no `unverified-read` line is printed

#### Scenario: TypeScript read
- **WHEN** `const SECTIONS = ['columns'] as const` is rewritten for `d[s]` and the loop also holds `log(s)`
- **THEN** the `log(s)` read is listed with the same template

### Requirement: String-named accesses on untyped receivers are a check of their own
A string-named access SHALL be a string-member form of the language registry, a Python field-name read
(`model_fields`, `model_fields_set`), or a TypeScript element access `x['NAME']`, whose member is the plain string
literal NAME. One whose object the checker types as unknown (Python `Unknown`, `Any` or a union holding either;
TypeScript `any`), or (Python) whose callee the checker cannot resolve while the call has the form's syntax, SHALL
be reported by the `string-blindspot` check and never by `attr-blindspot`, with `compliance.string-blindspot`, or
with `compliance.string-blindspot-silent` when the registry marks the call as raising no error on a miss: Python's
`hasattr`, and `getattr` called with a default. `{receiver}` and `{type}` SHALL be as for `attr-blindspot`.
`{site}` SHALL be the access with each run of whitespace collapsed to one space and the member printed as
`'NAME'`: `CALLEE(RECEIVER, 'NAME')` for a call, followed by `, …` before the closing parenthesis when the call
passes further arguments; `RECEIVER['NAME']` for an element access; and the read as written for a field-name read
(`RECEIVER.model_fields['NAME']`, `RECEIVER.model_fields.get('NAME')`, `'NAME' in RECEIVER.model_fields`).

#### Scenario: Python call forms
- **WHEN** `dr-compliance --attr columns` runs on a file holding, with `x: Any`, `getattr(x, "columns")`,
  `setattr(x, "columns", 1)` and `patch.object(x, "columns")`
- **THEN** stdout holds `string-blindspot: getattr(x, 'columns') — x is Any, so a rename of .columns is
  unverifiable`, `string-blindspot: setattr(x, 'columns', …) — …` and `string-blindspot: patch.object(x, 'columns')
  — …`, each after its path and line

#### Scenario: TypeScript forms
- **WHEN** `dr-compliance --attr columns` runs on a file holding, with `x: any`, `Reflect.get(x, 'columns')` and
  `x["columns"]`
- **THEN** stdout holds `string-blindspot: Reflect.get(x, 'columns') — x is any, so a rename of .columns is
  unverifiable` and `string-blindspot: x['columns'] — …`

#### Scenario: Multiline receiver
- **WHEN** the object argument spans two lines inside parentheses
- **THEN** `{site}` and `{receiver}` print it with its whitespace collapsed

## MODIFIED Requirements

### Requirement: Compliance check sets are per language
Each language's `dr-compliance` checks SHALL be listed in the language registry. Without `--select`, every
check of each file's language SHALL run. A selected id that no language lists SHALL exit 2; a selected id that
only another language lists SHALL not apply to a file. Python's checks SHALL be `untyped-def`,
`unannotated-attr`, `explicit-any`, `mock`, `rope-walk`, `attr-blindspot` and `string-blindspot`; TypeScript's SHALL
be `tsconfig`, `explicit-any`, `untyped-def`, `mock`, `attr-blindspot` and `string-blindspot`. The attribute checks,
`attr-blindspot` and `string-blindspot`, SHALL each run only when selected (or no `--select` is given) and `--attr
NAME` is given. A `--select` naming an attribute check without `--attr` SHALL print `compliance.attr-required`,
`{check}` the first attribute check `--select` names, on stderr and exit 2; `--attr` with a `--select` that names
no attribute check SHALL print `compliance.attr-unselected` on stderr and exit 2. Every kind a `dr-compliance`
finding prints, other than `parse-error`, SHALL be a registry check id. On files rope's walker fully covers and that
reference no `Any`, Python's output without `--attr` SHALL be unchanged.

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
- **THEN** stderr is `compliance.attr-required` naming `attr-blindspot`, stdout is empty and the exit code is 2

#### Scenario: --attr outside the selection
- **WHEN** `dr-compliance --select untyped-def --attr formula pkg` runs
- **THEN** stderr is `compliance.attr-unselected`, stdout is empty and the exit code is 2

#### Scenario: Selecting string-blindspot
- **WHEN** `dr-compliance --select string-blindspot --attr formula pkg` runs on files holding `o.formula` and
  `getattr(o, "formula")` with `o: Any`
- **THEN** only the `string-blindspot` line of the `getattr` call is printed and the exit code is 1

#### Scenario: Selecting attr-blindspot leaves string forms out
- **WHEN** `dr-compliance --select attr-blindspot --attr formula pkg` runs on the same files
- **THEN** only the `attr-blindspot` line of `o.formula` is printed

#### Scenario: string-blindspot without --attr
- **WHEN** `dr-compliance --select string-blindspot pkg` runs
- **THEN** stderr is `compliance.attr-required` naming `string-blindspot`, stdout is empty and the exit code is 2

#### Scenario: Both attribute checks by default
- **WHEN** `dr-compliance --attr formula pkg` runs without `--select` on the same files
- **THEN** both lines are printed, sorted by path, line and column

### Requirement: TypeScript compliance checks
The TypeScript checks SHALL be: `tsconfig`, one finding per governing tsconfig and per flag whose effective
value after `extends` resolution is not true, among `strict`, `noImplicitAny` and `noImplicitOverride`;
`explicit-any`, every `any` type in the file; `untyped-def`, every parameter, binding element or rest parameter
whose type is implicitly `any` as the type checker determines it with `noImplicitAny` in force (return types
are not required); `mock`, the TypeScript mock-lint rules; `attr-blindspot`, which with `--attr NAME` SHALL
report `x.NAME` accesses whose receiver's type is `any`; and `string-blindspot`, which with `--attr NAME` SHALL
report `x['NAME']` (a plain string literal) accesses whose receiver's type is `any`, and each TypeScript
string-member form of the language registry whose member argument is the plain string literal `NAME` and whose
object argument's type is `any`.
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
- **THEN** that call is reported as `string-blindspot`, printed `vi.spyOn(o, 'id')`, with receiver `o` and `{type}` `any`

#### Scenario: Element access on an any object
- **WHEN** `--attr id` runs on a file with `function k(o: any) { return o['id'] }`
- **THEN** that access is reported as `string-blindspot`, printed `o['id']`, and `--select attr-blindspot` does not
  report it

### Requirement: Member renames refuse on untyped receivers
A member rename SHALL be a `dr-refactor rename` whose symbol is declared in a class body: in Python a method (sync
or async), property, class attribute, instance attribute (`self.x`) or field; in TypeScript a property, method or
accessor of a class, interface or type literal. A blind spot of the old name OLD SHALL be, in a source file of the
rename's language under the project:
- an attribute access `x.OLD` whose receiver the checker types as unknown (Python `Unknown`, `Any` or a union
  holding either; TypeScript `any`);
- a string-named access of OLD (a string-member form, a Python field-name read, a TypeScript `x['OLD']`) whose
  object is typed so, or whose callee the checker cannot resolve while the call has the form's syntax (the form's
  attribute path and the member argument a plain string literal exactly OLD);
- a Python dotted patch target whose first segment names a project top-level package, one of whose segments is
  OLD, and that does not resolve statically to exactly one declaration, or whose call has a target form's syntax
  while its callee does not resolve.

Before writing or printing a diff, a member rename SHALL find every blind spot outside a `--keep` site. With any,
it SHALL print one line per site on stderr, sorted by path, line and column (`compliance.attr-blindspot` for an
attribute access, `compliance.string-blindspot` or `compliance.string-blindspot-silent` for a string-named access,
`refactor.unresolved-target` for a dotted target), then `refactor.blindspots`, print
nothing on stdout, write nothing and exit 1, with or without `--apply`. With `--allow-blindspots` the same lines
SHALL be printed on stderr and the rename SHALL proceed. The set of blind spots SHALL equal what
`dr-compliance --select attr-blindspot,string-blindspot --attr OLD <project>` reports, the
project directory expanded as the routing rules expand a directory (Python's `excluded_dirs` naming virtualenv,
version-control and tool-cache directories), plus the unresolved targets and the mixed targets.

#### Scenario: Untyped fixture parameter refuses the rename
- **WHEN** method `Storage.get_model` is renamed and a test function holds `def test_a(storage): storage.get_model("m")`
- **THEN** stderr ends with the `attr-blindspot` line for `storage.get_model` followed by `refactor.blindspots`, stdout is
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
- **THEN** the call is a blind spot, printed as `string-blindspot`, and the rename refuses

#### Scenario: Non-member renames are not scanned
- **WHEN** a module-level function or a parameter is renamed while untyped `x.old` accesses exist
- **THEN** no blind-spot refusal occurs

#### Scenario: TypeScript any receiver
- **WHEN** property `Store.getModel` is renamed in TypeScript and a file holds `function g(o: any) { return o.getModel() }`
- **THEN** the rename refuses with that site's `attr-blindspot` line, `{type}` `any`

#### Scenario: TypeScript element access on an any receiver
- **WHEN** property `Store.getModel` is renamed and a file holds `function g(o: any) { return o['getModel']('a') }`
- **THEN** the rename refuses with that site's `string-blindspot` line, and `dr-compliance --select string-blindspot
  --attr getModel` reports the same line

#### Scenario: Virtualenv skipped by both
- **WHEN** a Python member rename's project holds `.venv/lib/x.py` with an untyped `o.OLD`
- **THEN** neither the rename nor `dr-compliance --select attr-blindspot --attr OLD <project>` reports it

#### Scenario: String-named access with a default
- **WHEN** attribute `Ds.columns` is renamed with `--allow-blindspots` and a module holds `def a(x: Any): return
  x.columns` and `def b(x: Any): return getattr(x, "columns", None)`
- **THEN** the first site prints `attr-blindspot` and the second prints the `compliance.string-blindspot-silent` line
  `getattr(x, 'columns', …) — x is Any, so a rename of .columns is unverifiable and a miss raises no error`

### Requirement: Python --attr reports Unknown and Any receivers
Python `dr-compliance --attr NAME` SHALL report, as the `attr-blindspot` check, every access `x.NAME` whose receiver
basedpyright types as `Unknown`, `Any`, or a union containing either, with the shared `compliance.attr-blindspot`
finding; and, as the `string-blindspot` check, every Python string-named access (a string-member form of the
language registry, a field-name read) whose member is the plain string literal `NAME` and whose object is typed so
or whose callee basedpyright cannot resolve while the call has the form's syntax, with
`compliance.string-blindspot` or `compliance.string-blindspot-silent`. `{receiver}` SHALL be the receiver's (or
object argument's) source text with
each run of whitespace collapsed to one space, and `{type}` SHALL be `Unknown` or `Any` (`Unknown` when both occur,
and for an unresolved callee). Findings SHALL be one per access or call position, sorted by path, line and column.
The verdict at each position SHALL come from the same occurrence index a rename uses, so a site `--attr NAME`
reports is exactly a blind spot a member rename of `NAME` reports there, with the same kind.
basedpyright SHALL start only when `--attr` is given, with the working directory as its workspace, under the same
conditions as for `dr-refactor`. A language server that cannot start, is not patched, fails or exits SHALL make the
command print the `compliance.pyright-failed` finding on stderr and exit 2. The TypeScript twin's `--attr` output
SHALL use the same templates with `{type}` `any`.

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
- **THEN** both are reported as `string-blindspot`: the `getattr` call with receiver `m`, printed `getattr(m,
  'formula')`, and the `monkeypatch.setattr` call (unresolved callee) with receiver `obj` and `{type}` `Unknown`,
  printed `monkeypatch.setattr(obj, 'formula', …)`

#### Scenario: Same verdict as a rename
- **WHEN** `--attr formula` and a dry-run rename of member `Model.formula` run on the same project
- **THEN** the positions and kinds `--attr` reports are exactly those of the rename's blind spots

#### Scenario: Language server failure
- **WHEN** `--attr` runs and the language server cannot start
- **THEN** stderr is the `compliance.pyright-failed` finding and the exit code is 2

#### Scenario: TypeScript output unchanged
- **WHEN** `--attr id` runs on a TypeScript file with `function g(o: any) { return o.id }`
- **THEN** stdout is byte-identical to the golden before this change

#### Scenario: Calls whose miss raises no error
- **WHEN** `--attr formula` runs on a file holding `def t(m): return hasattr(m, "formula")` and `def u(m): return
  getattr(m, "formula", None)`
- **THEN** both are reported with `compliance.string-blindspot-silent`, printed `hasattr(m, 'formula')` and
  `getattr(m, 'formula', …)`

#### Scenario: Field-name read on an untyped receiver
- **WHEN** `--attr formula` runs on a file holding `def v(m): return m.model_fields["formula"]`
- **THEN** that subscript is reported as `string-blindspot`, printed `m.model_fields['formula']`

### Requirement: Literal members are renamed where the checker types them
A rename located at a member of a string-literal type (`--symbol Q['value']`, or a locator on that string inside
the type) SHALL take the new value from `--new-name`: any text without a quote character (`'`, `"` or a backtick), a
backslash, `${`, a NUL character or a line break (U+2028 and U+2029 included) (else exit 2 with `refactor.literal-value`); the identifier rule SHALL NOT apply, and each rewritten string SHALL
keep its quote style.

- TypeScript: the rewritten strings SHALL be the language service's rename locations for that string. The rename
  SHALL then check the edited program in memory, in every project holding an edited file, and compare it with the
  program before the edit, each position mapped back through the edits.
- Python: the rename SHALL probe the checker in la's language server, in memory, with the member replaced by a
  sentinel. A string literal exactly OLD SHALL be rewritten when, under the probe, a new diagnostic's range is that
  literal or a list, tuple, set or dict display holding it as an element or key, or when the type the checker gives
  its comparison operand (`==`, `!=`, `is`, `is not`), `in` container or `match` subject contains the sentinel. The
  rename SHALL then probe with the member and every such literal set to the sentinel.

In both languages, a checker diagnostic absent before the rename whose range is a name or dotted name with literal
sources (see "A string held by a name is followed to its literal sources") SHALL rewrite each source literal
exactly OLD, and the check SHALL repeat with those sources rewritten. Each diagnostic absent before the rename that
then remains SHALL be a blind spot, `refactor.literal-unresolved`, joining the blind-spot refusal (`--keep` and
`--allow-blindspots` apply). All of this SHALL hold whatever import route carries the member's type to a file.

Every other string literal whose whole value is OLD SHALL be unchanged and listed as a `leftover` with `{where}`
`string`, with or without `--docs`, except one at a position where the checker accepts no other string (TypeScript:
a sentinel string is not assignable to its contextual type; Python: a sentinel in its place draws a diagnostic on it
that was absent before), which is typed by a literal type the rename leaves unchanged and SHALL NOT be listed.

#### Scenario: Python contexts
- **WHEN** `DriftKind = Literal["edit_model", "drop"]` is renamed at `DriftKind['edit_model']` to `edit_master`, and
  the project holds a call `f("edit_model")` with `f(kind: DriftKind)`, `k: DriftKind = "edit_model"`, a return
  of `"edit_model"` from a function returning `DriftKind`, a default `kind: DriftKind = "edit_model"`, `xs:
  list[DriftKind] = ["edit_model"]`, `kind == "edit_model"`, `kind in ("edit_model",)` and `case "edit_model":`
  on a `DriftKind` subject
- **THEN** every one of those strings becomes `"edit_master"`, with its quote style kept

#### Scenario: Unrelated equal strings untouched
- **WHEN** the project also holds `Other = Literal["edit_model", "zzz"]` with `g("edit_model")` for `g(o: Other)`,
  `s: str = "edit_model"` and `choices=["edit_model"]`
- **THEN** none of them changes, the `str` and `choices` strings are listed as `leftover` with and without
  `--docs`, and the `Other` argument is not listed

#### Scenario: Position that accepts any string is listed
- **WHEN** the project also holds `h("edit_model")` for `h(o: Other | str)`, and `g("edit_model")` on a line whose
  argument already has a checker error
- **THEN** both are unchanged and listed as `leftover`

#### Scenario: Exhaustive match does not refuse
- **WHEN** a `match` on a `DriftKind` subject handles every value and ends with `assert_never(kind)`
- **THEN** its `case "edit_model":` is rewritten and no blind spot is reported

#### Scenario: Derived alias
- **WHEN** `Ext = Literal[DriftKind, "x"]` types an argument `h("edit_model")`
- **THEN** that string is rewritten

#### Scenario: Every import route carries the type
- **WHEN** a Python file reaches the module declaring `DriftKind` only through one of: a chain of re-exports,
  `from m import *`, a relative import, an import under `if TYPE_CHECKING:`, an import inside a function, a `.pyi`
  stub, an `__init__.pyi`, a `<name>-stubs` directory, a namespace package, or a project `__builtins__.pyi`; and
  the file passes `"edit_model"` to a parameter typed `DriftKind`
- **THEN** that string is rewritten in each such file

#### Scenario: Equal string in a file outside the member's reach
- **WHEN** a file whose imports never reach the module declaring `DriftKind` holds `s: str = "edit_model"`
- **THEN** that string is unchanged and listed as `leftover`

#### Scenario: TypeScript contexts
- **WHEN** `type Kind = 'edit_model' | 'drop'` is renamed at `Kind['edit_model']`, and the project holds a typed
  variable, an argument, `x === 'edit_model'`, a `case`, a typed array element, an equal string in another union,
  a `string` variable and an imported use of `Kind`
- **THEN** the typed variable, argument, comparison, case, array element and imported use change, and the other
  union's string and the `string` variable do not

#### Scenario: Value with a quote refused
- **WHEN** `--new-name` is `it's`
- **THEN** stderr ends with `refactor.literal-value` and the exit code is 2

#### Scenario: Narrowed local refuses
- **WHEN** a function binds `k = "drop"`, then `k = "edit_model"`, and later calls `f(k)`
- **THEN** the call site is a `refactor.literal-unresolved` blind spot and the rename refuses with exit 1

#### Scenario: Blind spot in a file without the string
- **WHEN** a module binds `DEFAULT` to `"edit_model"` in one branch of an `if` and to `"drop"` in the other, and
  another file that holds no string `"edit_model"` and reaches `DriftKind` through any route above passes `DEFAULT`
  to a parameter typed `DriftKind`
- **THEN** that call site is a `refactor.literal-unresolved` blind spot and the rename refuses with exit 1

#### Scenario: Local with a single source
- **WHEN** a function holds `k = "edit_model"` and later `f(k)`
- **THEN** the literal becomes `"edit_master"`, the call is unchanged and no blind spot is reported

#### Scenario: Constant read in a file without the string
- **WHEN** a module holds `DEFAULT: Final = "edit_model"`, and another file that holds no string `"edit_model"`
  and reaches `DriftKind` through any route above passes `DEFAULT` to a parameter typed `DriftKind`
- **THEN** the constant's literal becomes `"edit_master"` and the rename exits 0

#### Scenario: Value with two sources refuses
- **WHEN** a function holds `v = "edit_model" if c else "drop"` and later `f(v)`
- **THEN** the call site is a `refactor.literal-unresolved` blind spot and the rename refuses with exit 1

#### Scenario: Source also typed by another literal type
- **WHEN** `KIND = "edit_model"` is passed to `f(kind: DriftKind)` and to `g(o: Other)` with `Other =
  Literal["edit_model", "zzz"]`
- **THEN** the `g(KIND)` site is a `refactor.literal-unresolved` blind spot, the rename refuses with exit 1 and no
  file changes

#### Scenario: TypeScript edit that breaks the program refuses
- **WHEN** `type Kind = 'edit_model' | 'drop'` is renamed at `Kind['edit_model']` and a file holds `const v = c ?
  'edit_model' : 'drop'` followed by `take(v)` with `take(k: Kind)`
- **THEN** stderr holds that call's `refactor.literal-unresolved` line and `refactor.blindspots`, stdout is empty, the
  exit code is 1 and no file changes; with `--allow-blindspots` the diff is printed and the exit code is 0

#### Scenario: TypeScript error present before the rename
- **WHEN** the project already has a checker error on a line the rename does not edit
- **THEN** that error is not a blind spot and the rename exits 0
