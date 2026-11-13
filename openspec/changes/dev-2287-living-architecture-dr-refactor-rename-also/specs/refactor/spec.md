## ADDED Requirements

### Requirement: Python renames include every reference basedpyright resolves
For a Python `rename` of a symbol other than a module, `dr-refactor` SHALL add to rope's edits every reference
basedpyright resolves to each declaration the rename renames: every declaration of the renamed hierarchy by default,
only the located one with `--no-in-hierarchy`. These references SHALL include forward-reference strings (`"X"`,
`Optional["X"]`, `list["X"]`, `"X | None"`), keyword arguments of dataclass and Pydantic fields at calls whose callee
is the owning class, a subclass or a `type[...]` of either, receivers typed by a parameter annotation, an attribute
annotation (`self.x: T` or a class-body `x: T`), a return annotation or inference, `isinstance`-narrowed receivers,
and `super().name(...)` calls. Every added edit SHALL replace exactly the old name, located by source character in
the file's text as read; positions SHALL be correct after non-ASCII and astral characters and with CRLF line endings.
Edits SHALL NOT overlap unless identical; identical edits SHALL be merged. When a file changes between its read and
the write, nothing SHALL be written. A module rename SHALL keep rope's behaviour alone.

basedpyright SHALL be the version the PyPI twin ships, started from la's own environment, run with la's
pyright#11919 patch, reading the project's own configuration and finding the project's interpreter as basedpyright
does. It SHALL run with its working directory outside the project, without the user site, without bytecode
writing and without the working directory on the interpreter's path, so no target-repo code runs. A language server
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

### Requirement: Python async definitions rename like sync ones
The Python `dr-refactor rename` SHALL rename an `async def` method or function located by `--line`/`--col`,
`--offset` or `--name`, at its definition or at a call: its definition, its overrides in the renamed hierarchy and
every call it would rename for the same code without `async`.

#### Scenario: Async method from its definition
- **WHEN** `class A` has `async def get_model(self, x: int) -> None: ...`, `class B(A)` overrides it with an `async
  def`, and a function holds `a = A()` and `await a.get_model(1)`, and the rename names `get_model` in `A` by
  `--line`/`--col`
- **THEN** both definitions and the call are renamed and the exit code is 0

#### Scenario: Async function from a call
- **WHEN** a module-level `async def fetch()` is renamed by `--offset` of one of its calls
- **THEN** the definition and every call are renamed

### Requirement: Python rename refusals are findings
When rope refuses to rename the location, the Python `dr-refactor` SHALL print the `refactor.cannot-rename` finding on
stderr, write nothing and exit 1. No traceback or library message text SHALL be printed.

#### Scenario: Location that is not an identifier
- **WHEN** `rename --offset` points at whitespace between two statements
- **THEN** stderr is the `refactor.cannot-rename` finding and the exit code is 1

### Requirement: Python field renames rewrite the keyword arguments of the owning class
A keyed class SHALL be a `pydantic.BaseModel` subclass or a `TypedDict`. When the renamed symbol is a field of a keyed
class K, the Python `dr-refactor` SHALL also rewrite the keyword `old=` in `cls(old=...)` where basedpyright types
`cls` as `type` of K or of a subclass, and in `X.model_construct(old=...)` where `X` resolves to K or a subclass and
`model_construct` resolves to Pydantic's `BaseModel.model_construct`. Any other call SHALL be unchanged.

#### Scenario: cls in a classmethod
- **WHEN** field `Model.columns` is renamed and `class Model2(Model)` has a classmethod returning `cls(columns=[])`
- **THEN** the keyword becomes `fields=`

#### Scenario: model_construct
- **WHEN** a module calls `Model.model_construct(columns=[])`
- **THEN** the keyword becomes `fields=`

#### Scenario: Rebound cls and unrelated model_construct
- **WHEN** a classmethod rebinds `cls = Other` before `cls(columns=[])`, and an unrelated class defines its own
  `model_construct(columns=...)`
- **THEN** neither call changes

### Requirement: Python field renames rewrite typed dict keys
When the renamed symbol is a field of a keyed class K, the Python `dr-refactor` SHALL rewrite the key `"old"` in a
dict literal whose target is K or a subclass, at these targets:
- the argument of `X.model_validate(...)`, of `X(**...)` and of `X.model_construct(**...)`, where `X` resolves to K
  or a subclass (including `cls` typed so);
- the `update=` argument of `x.model_copy(update=...)` where `x` is typed K or a subclass;
- for a `TypedDict` K, an argument to a parameter annotated K, a value assigned to a variable annotated K, and a value
  returned from a function annotated to return K;
- a dict literal nested at the value of a rewritten-target key or keyword whose field type, after removing `None`
  from a union and unwrapping `list`, `Sequence`, `set`, `frozenset`, `tuple` and the values of `dict[str, ...]`, is
  a keyed class;
- a name bound exactly once in its scope, by `name = {...}`, declared neither `global` nor `nonlocal`, not captured by
  an inner scope, whose every use is one of the arguments above.

It SHALL also rewrite the string `"old"` among the elements of a set or dict literal given as `include=` or
`exclude=` to `x.model_dump(...)` or `x.model_dump_json(...)` where `x` is typed K or a subclass, recursing into a
nested dict literal through the field types as above.

A key SHALL be rewritten only when looking the field up in the target class's method resolution order lands on one
of the renamed declarations. The target SHALL be left unchanged when its type is `Unknown`, `Any`, a type variable,
or a union other than one keyed class with `None`. Only a plain string literal whose source text between its quotes
is exactly the old name SHALL be rewritten, and only those characters SHALL change. Keys of a field declaring
`alias` or `validation_alias`, and of a model whose configuration sets an `alias_generator`, SHALL be unchanged.
A rewritten key or keyword whose new name the same literal or call already holds SHALL make `dr-refactor` print the
`refactor.name-conflict` finding naming that file and line, write nothing and exit 1.

#### Scenario: model_validate and unpacked dict
- **WHEN** field `Model.columns` is renamed and modules hold `Model.model_validate({"columns": []})` and
  `Model(**{"columns": []})`
- **THEN** both keys become `"fields"` with their quote style kept

#### Scenario: Nested member dicts
- **WHEN** `Member.type` is renamed, `Model.columns` is `list[Member]`, and a module holds
  `Model.model_validate({"columns": [{"name": "a", "type": "INT"}]})` and `Model(columns=[{"type": "INT"}])`
- **THEN** only the `"type"` keys inside the member dicts change

#### Scenario: model_copy and model_dump
- **WHEN** `m: Model` and a module holds `m.model_copy(update={"columns": []})` and
  `m.model_dump(exclude={"columns"})`
- **THEN** both `"columns"` strings become `"fields"`

#### Scenario: TypedDict flows
- **WHEN** key `columns` of `class ModelDict(TypedDict)` is renamed and a module passes `{"columns": []}` to
  `def f(d: ModelDict)`, assigns `x: ModelDict = {"columns": []}` and returns `{"columns": []}` from
  `def g() -> ModelDict`
- **THEN** all three keys become `"fields"`

#### Scenario: Dict variable bound once
- **WHEN** a function holds `raw = {"columns": []}` followed only by `Model.model_validate(raw)`
- **THEN** the key becomes `"fields"`

#### Scenario: Dict variable with another use
- **WHEN** the function also reads `raw["columns"]`, mutates `raw`, aliases it, captures it in a closure, or unpacks
  it into another literal
- **THEN** no key of that literal changes

#### Scenario: Untyped and ambiguous targets
- **WHEN** keys `"columns"` reach `u.model_validate(...)` with `u: Any`, `def h(d: dict[str, Any])`, a target typed
  `Model | Other` where `Other` is another keyed class, and a target typed by an unconstrained type variable
- **THEN** none of those keys change

#### Scenario: A same-named field of another class
- **WHEN** `Other` also has a field `columns` and a module holds `Other.model_validate({"columns": []})`
- **THEN** that key is unchanged

#### Scenario: Aliased field
- **WHEN** the renamed field is declared `columns: list[Member] = Field(alias="cols")`, or the model's configuration
  sets an `alias_generator`
- **THEN** no dict key changes

#### Scenario: Non-plain key literal
- **WHEN** a target dict holds the key `"col" "umns"` or `"\x63olumns"`
- **THEN** that key is unchanged

#### Scenario: Key collision
- **WHEN** a target dict holds both `"columns"` and `"fields"`, or a call passes both `columns=` and `fields=`
- **THEN** stderr is the `refactor.name-conflict` finding naming that file and line, the exit code is 1 and no file
  changes

### Requirement: Python field renames refuse an unresolved owner chain
When the renamed symbol is a field of a class whose chain of bases holds a base basedpyright cannot resolve, the
Python `dr-refactor` SHALL print the `refactor.unresolved-base` finding naming the class, the file and the line of that
base, write nothing and exit 1. A rename of a class, function, method or module SHALL NOT be refused for this reason.

#### Scenario: Pydantic not resolvable
- **WHEN** the project's interpreter does not have `pydantic` and a field of `class Model(BaseModel)` is renamed
- **THEN** stderr is the `refactor.unresolved-base` finding naming `Model` and the line of its base, the exit code is
  1 and no file changes

#### Scenario: Method rename proceeds
- **WHEN** a method of the same class is renamed
- **THEN** the rename proceeds and exits 0

### Requirement: Python --attr reports Unknown and Any receivers
Python `dr-compliance --attr NAME` SHALL report every access `x.NAME` whose receiver basedpyright types as `Unknown`,
`Any`, or a union containing either, with the shared `compliance.attr-blindspot` finding: `{receiver}` SHALL be the
receiver's source text with each run of whitespace collapsed to one space, and `{type}` SHALL be `Unknown` or `Any`
(`Unknown` when both occur). Findings SHALL be one per access position, sorted by path, line and column. basedpyright
SHALL start only when `--attr` is given, with the working directory as its workspace, under the same conditions as
for `dr-refactor`. A language server that cannot start, is not patched, fails or exits SHALL make the command print
the `compliance.pyright-failed` finding on stderr and exit 2. The TypeScript twin's `--attr` output SHALL use the same
template with `{type}` `any`, unchanged byte for byte.

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

#### Scenario: Language server failure
- **WHEN** `--attr` runs and the language server cannot start
- **THEN** stderr is the `compliance.pyright-failed` finding and the exit code is 2

#### Scenario: TypeScript output unchanged
- **WHEN** `--attr id` runs on a TypeScript file with `function g(o: any) { return o.id }`
- **THEN** stdout is byte-identical to the golden before this change

## MODIFIED Requirements

### Requirement: Refactors edit only at references
In both languages, a file that `dr-refactor` touches SHALL change only within these permitted regions: the span of each
resolved reference to the renamed or moved module or symbol, including the name inside a forward-reference string
and, for a Python field rename, the name inside a typed dict key or `model_dump` element and a keyword argument's
name; the import item holding such a reference (its whole statement, or its whole line, when it is the statement's
only item); one inserted import statement directly after a referencing import statement or after the leading import
block; and, for `move-symbol`, the moved code's region. Every other byte SHALL be unchanged: no import SHALL be
reordered, merged, hoisted or reformatted, and no non-import statement SHALL move. A `from` import SHALL be split only
when exactly one of its names moves. CRLF line endings and a missing final newline SHALL be preserved.

#### Scenario: importorskip-gated import stays gated
- **WHEN** `move-module` or `move-symbol` runs and a touched test file has `x = pytest.importorskip("x")` followed by
  `import x.y`
- **THEN** both lines keep their positions and text, and the only changed lines are the moved references

#### Scenario: Non-import statement between import groups
- **WHEN** a touched file has `sys.path.insert(0, ".")` between two import groups and one group imports the moved
  module
- **THEN** the statement and both groups keep their order, and only the referencing import line changes

#### Scenario: Unsorted import block untouched
- **WHEN** a touched file's import block is not in sorted order and one line imports from the moved module
- **THEN** only that line's module path changes, and every other line of the block is byte-identical

#### Scenario: Module rename leaves the shapes intact
- **WHEN** `rename` renames module `client` to `cli2` across files holding the gated, interleaved, unsorted,
  multi-name and function-local import shapes
- **THEN** only the module name tokens and the uses bound to them change

#### Scenario: TypeScript import split in place
- **WHEN** `move-symbol` moves `f` out of `src/a.ts` and `test/t.ts` has `import { g, f } from "../src/a.js";`
  followed by other imports and a statement between import groups
- **THEN** that line becomes `import { g } from "../src/a.js";`, the next line imports `f` from the new file, and
  every other line is byte-identical

#### Scenario: String and key edits are name-only
- **WHEN** a Python field rename rewrites `r'columns'` as a typed dict key and class `Rec` inside `'Rec | None'`
- **THEN** only the name characters change, and the prefixes, quotes and the rest of each string are byte-identical

### Requirement: TypeScript rename
`rename` SHALL rename every reference the TypeScript language service finds, including overrides and
implementations across the hierarchy, and SHALL keep the shape of shorthand properties and import/export
aliases. Strings and comments SHALL NOT be rewritten. `--no-in-hierarchy` and `--unsure include` SHALL exit 1
with a not-supported finding; the default `--unsure skip` SHALL be accepted. A symbol that cannot be renamed,
such as one declared in a library or a declaration file, SHALL exit 1 with a stable finding.

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
