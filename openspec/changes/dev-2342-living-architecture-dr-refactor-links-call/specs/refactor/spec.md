## ADDED Requirements

### Requirement: Python parameter renames link keywords through the checker's signature
For a Python parameter rename, a `name=` keyword of a call that the checker resolves to no declaration SHALL be linked
to the renamed parameter when, in every callable alternative the checker considers at that call (each overload, each
member of a union), the callee's signature binds the keyword to a parameter named `old` in the code as it is, and binds
`new` to the same parameter once every renamed declaration is renamed, as the checker types the renamed text held in
memory. A linked keyword SHALL be rewritten like one the checker resolves. A keyword that is not linked in every
alternative SHALL NOT be rewritten by this rule. The rule SHALL depend on no list of decorators or wrappers. The checker
SHALL be asked in a number of requests that does not depend on the number of keywords, and in none when the run has no
such keyword; nothing SHALL be written to the project for it.

#### Scenario: Context-manager decorators
- **WHEN** `@asynccontextmanager async def engine(*, models: list[int])` and `@contextmanager def sync_engine(*, models:
  list[int])` each have `models` renamed to `datasets`, and another module holds `async with engine(models=[1]) as e:`
  and `with sync_engine(models=[1]) as s:`
- **THEN** each rename rewrites its declaration, its body uses and its call's keyword, and the exit code is 0

#### Scenario: Signature-preserving user decorator
- **WHEN** `def logged(fn: Callable[P, R]) -> Callable[P, R]` wraps with `functools.wraps`, `@logged def wrapped(*,
  models: list[int])` has `models` renamed, and a function calls `wrapped(models=[1])`
- **THEN** the declaration, the body use and the keyword are renamed

#### Scenario: Decorated method through a typed receiver
- **WHEN** `class C` declares `@contextmanager def scope(self, *, models: list[int])`, a function holds
  `with c.scope(models=[1]):` with `c: C`, and `models` is renamed
- **THEN** the declaration, the body use and the keyword are renamed

#### Scenario: One overload does not bind the keyword
- **WHEN** a decorated callee's type at a call is a union of two callables, and renaming the declaration changes `old`
  to `new` in only one of them
- **THEN** the keyword is not rewritten by this rule

#### Scenario: No extra request without unresolved keywords
- **WHEN** a parameter rename runs over a project whose every `old=` keyword the checker resolves
- **THEN** the run sends the same number of export requests as before this change

### Requirement: Python renames follow keywords through **kwargs carriers
A carrier SHALL be a `def` or `async def` with a `**kw` parameter. Its sinks SHALL be:
- `X(**kw)`, where the checker resolves `X` to a keyed class (a key names the field its method resolution order holds),
  to a function or method (a key names its positional-or-keyword or keyword-only parameter), to any other class (a key
  names a parameter of the `__init__` or `__new__` the checker resolves the call to), or to another carrier (a key that
  is none of that carrier's own parameters continues into its flow). A function or method sink whose `def` is decorated
  SHALL count only when the checker's signature at the sink binds `old` in the code as it is and `new` once the renamed
  declarations are renamed; otherwise the sink is unresolved;
- `X.model_construct(**kw)`, `X.model_validate(kw)` and `x.model_copy(update=kw)`, as the requirement on typed dict
  keys targets them;
- `super().__init__(**kw)`: the function the checker resolves it to, or, when that is Pydantic's `BaseModel.__init__`,
  the enclosing class as a keyed class;
- a dict literal holding `**kw` (`{..., **kw}`), whose sinks are the literal's own: the literal at one of the sinks
  above, unpacked there (`X(**{..., **kw})`), or bound to a name bound exactly once in its function scope whose every
  use is at such a sink.

A key form SHALL be `kw["s"]` (read, assigned or deleted), `kw.get("s", ...)`, `kw.pop("s", ...)`,
`kw.setdefault("s", ...)`, `"s" in kw` or `"s" not in kw`, with `s` a plain string literal. A neutral use SHALL be `kw`
tested for truth or passed to the builtin `len`. A carrier SHALL be resolved when every use of its `**kw` name in its body is a
sink, a key form or a neutral use and every sink's callee resolves; any other use (an alias, a copy, `update`, `|`, `kw`
as a plain argument, `return kw`, iteration, `items()`, `keys()`, `values()`, a key that is not a plain string literal,
a rebinding, a use in a nested scope) SHALL make it unresolved. A same-named binding of a nested scope is not a use.
For a rename to `new`, a carrier that declares a parameter `new` a keyword can bind, holds a key form `"new"`, or holds
`**kw` in a dict literal with a constant key `"new"` SHALL be unresolved.

For a renamed field of a keyed class or a renamed parameter `old`, each sink of a carrier SHALL yield *renamed* (the
key `old` lands only on renamed declarations there), *other* (it lands on another declaration or on none), or
*unresolved*; a sink that is a carrier yields that carrier's verdict. A carrier's verdict SHALL be: *unresolved* when
the carrier is unresolved, any sink is unresolved, or the carrier calls itself through a chain of carriers; else *mixed*
when some sinks are renamed and some other; else *renamed* when every sink is renamed; else *other*.

For a carrier `F` whose verdict is renamed, `dr-refactor` SHALL rewrite the keyword `old=` of each call the checker
resolves to `F` where `old` is none of `F`'s own parameters, the constant key `"old"` of a dict literal unpacked into
such a call (`F(**{"old": v})`), and each key-form string `"old"` in `F`. For a verdict of other, nothing of `F` SHALL
change or be listed. The rewrites SHALL obey the rules of typed dict keys for aliased fields, alias generators, plain
string literals and collisions with the new name. A constant key `"old"` of a dict literal unpacked into a call the
checker resolves to a function, method or class other than a keyed class SHALL be rewritten when that key names a
renamed parameter there.

#### Scenario: Helper building a model
- **WHEN** `class Query(BaseModel)` has `source_model: str` and `measures: list[str] = []`, a module holds
  `def q(**kw: Any) -> Query:` with `kw.setdefault("source_model", "orders")` and `return Query(**kw)`, a test calls
  `q(measures=["n"])`, and `Query.measures` is renamed to `metrics`
- **THEN** the field and the call's keyword are renamed and the exit code is 0

#### Scenario: Key forms in the carrier
- **WHEN** the same helper also holds `kw["source_model"]`, `kw.get("source_model")`, `kw.pop("source_model", None)`
  and `"source_model" in kw`, and `Query.source_model` is renamed to `population`
- **THEN** every one of those strings and the `setdefault` string become `"population"` with their quotes kept, and no
  `leftover` line names them

#### Scenario: Chain of carriers
- **WHEN** `def q2(**kw: Any) -> Query: return q(**kw)` is called as `q2(measures=["n"])`
- **THEN** that keyword is renamed too

#### Scenario: Subclass constructor forwarding to the model
- **WHEN** `class Sub(Query)` declares `def __init__(self, **kw: Any) -> None: super().__init__(**kw)` and a module
  calls `Sub(measures=[])`
- **THEN** the keyword is renamed

#### Scenario: Dict literal carrying the keywords
- **WHEN** a carrier holds `return Query(**{"source_model": "orders", **kw})`, another holds
  `data = {"source_model": "orders", **kw}` followed only by `return Query.model_validate(data)`, and each is called
  with `measures=["n"]`
- **THEN** both keywords are renamed

#### Scenario: Dict literal unpacked into a carrier
- **WHEN** a module calls `q(**{"measures": ["n"]})`
- **THEN** the key becomes `"metrics"`

#### Scenario: Function and constructor sinks
- **WHEN** `def kwonly(*, model_name: str) -> str` has `model_name` renamed, `def wrap(**kw: str) -> str: return
  kwonly(**kw)` is called as `wrap(model_name="x")`; and separately `class Engine` with `def __init__(self, *, models:
  list[int])` has `models` renamed while `def make(**kw: Any) -> Engine: return Engine(**kw)` is called as
  `make(models=[1])`
- **THEN** both call keywords are renamed

#### Scenario: Carrier into another class
- **WHEN** `def other(**kw: Any) -> Other: return Other(**kw)` builds a class `Other` that also declares `measures`,
  it is called as `other(measures=[])`, and `Query.measures` is renamed
- **THEN** that call is unchanged and no line names it

#### Scenario: Nested scope shadowing the name
- **WHEN** a carrier's body holds a lambda or comprehension binding its own `kw`
- **THEN** that binding does not make the carrier unresolved

#### Scenario: Aliased field
- **WHEN** the renamed field is declared with `Field(alias="m")`
- **THEN** no carrier keyword, key or key-form string changes

#### Scenario: Keyword collision through a carrier
- **WHEN** a call holds `q(measures=[], metrics=[])` and `Query.measures` is renamed to `metrics`
- **THEN** stderr ends with the `refactor.name-conflict` finding naming that file and line, the exit code is 1 and no
  file changes

### Requirement: Parameter and field renames refuse on unlinked keywords
An unlinked keyword of a Python rename of a parameter, or of a field of a keyed class, SHALL be a keyword `old=` of a
call, or a constant key `"old"` of a dict literal unpacked into a call, in a project source file, that the rename's
other rules neither rewrite nor prove to land on another declaration, where:
- the callee expression resolves, as the checker resolves it (aliases and bound methods followed, a class through the
  constructors the checker resolves, any member of a union), to a function, method or class declaring a renamed
  parameter, while the callee's signature as the checker types it does not bind `old` there; or
- the callee resolves to a carrier whose verdict for `old` is mixed or unresolved; or
- the checker types the callee `Unknown`, `Any`, `Never` or a union holding one of them; or
- the callee is a class declaring both `__init__` and `__new__` with a parameter `old`, of which the run renames only
  one; or
- the key is in a dict literal unpacked into a call whose callee is neither a name nor an attribute access.

Unlinked keywords SHALL be blind spots of the rename: each SHALL print one `refactor.unlinked-keyword` line on stderr
(`{callee}` the callee's source text with each run of whitespace collapsed to one space), sorted with the other
blind-spot lines by path, line and column, followed by `refactor.blindspots`; the rename SHALL print nothing on stdout,
write nothing and exit 1, with or without `--apply`. With `--allow-blindspots` the per-site lines SHALL be printed without
`refactor.blindspots` and the rename SHALL proceed, leaving those keywords unchanged. A `--keep` covering a line SHALL drop its line. With `--unsure
include` every unlinked keyword and key SHALL also be rewritten, and blind spots SHALL be reported, refused and let
through as without it. `{names}` of `refactor.blindspots` SHALL list each old name with a blind spot once, a member's
as `.old` and an unlinked keyword's as `old=`, joined by `, `. A rename of a function, class, module, local or
non-field member SHALL NOT be scanned for unlinked keywords, and `dr-compliance` SHALL NOT report them.

#### Scenario: Signature-erasing decorator
- **WHEN** `@functools.lru_cache def cached(models: int) -> int` has `models` renamed, the checker types `cached`'s
  call signature without a parameter `models`, and a function calls `cached(models=1)`
- **THEN** stderr ends with the `refactor.unlinked-keyword` line for `cached(models=...)` followed by
  `refactor.blindspots` naming `models=`, stdout is empty, the exit code is 1 and no file changes

#### Scenario: Untyped decorator
- **WHEN** `def deco(fn): ...` is unannotated, `@deco def f(*, models: int)` has `models` renamed and a module calls
  `f(models=1)`
- **THEN** that call is listed as an unlinked keyword and the rename refuses

#### Scenario: Override flag proceeds
- **WHEN** the lru_cache rename runs with `--allow-blindspots`
- **THEN** the line is printed on stderr, the diff renames the declaration and its body, `cached(models=1)` is
  unchanged and the exit code is 0

#### Scenario: Renamed on request
- **WHEN** the same rename runs with `--unsure include --allow-blindspots`
- **THEN** `cached(models=1)` becomes `cached(datasets=1)`, stdout starts with the `refactor.unsure-warning` line and
  the line is still printed on stderr

#### Scenario: Kept line
- **WHEN** the same rename passes `--keep` naming the call's line
- **THEN** the rename proceeds, the call is unchanged and no blind-spot line is printed

#### Scenario: Unresolved carriers
- **WHEN** `Query.measures` is renamed and carriers each build `Query` from `kw` after, in turn, `d = kw`, `dict(kw)`,
  `kw.copy()`, `base.update(kw)`, `base | kw`, passing `kw` as a plain argument, `return kw`, `for k in kw`,
  `kw.items()`, `kw[name]` with a variable key, rebinding `kw`, reading `kw` in a nested function, and two carriers
  calling each other, each called with `measures=[]`
- **THEN** every one of those calls is listed as an unlinked keyword, the rename refuses, and no file changes

#### Scenario: Mixed sinks
- **WHEN** `def both(**kw: Any)` holds `Query(**kw)` and `Other(**kw)`, `Other` declares its own `measures`, and
  `both(measures=[])` is called
- **THEN** that call is listed as an unlinked keyword

#### Scenario: Dict literal into an unresolved carrier
- **WHEN** a module calls `g(**{"measures": []})` where `g` is an unresolved carrier
- **THEN** that line is listed as an unlinked keyword

#### Scenario: Untyped callee
- **WHEN** a test holds `def test_totals(make_query): make_query(measures=["n"])` with `make_query` unannotated, and
  `Query.measures` is renamed
- **THEN** that call is listed as an unlinked keyword and the rename refuses; with `make_query` annotated as a callable
  returning `Query` whose signature binds no `measures`, it is not listed

#### Scenario: Other renames are not scanned
- **WHEN** a function, a class or a method is renamed in a project holding `untyped(old=1)` calls
- **THEN** no unlinked-keyword line is printed

#### Scenario: Members and keywords in one report
- **WHEN** a `rename-map` renames a method with an untyped receiver access and a parameter with an unlinked keyword
- **THEN** `refactor.blindspots` counts both and names `.method_old, param_old=` in the entries' order

### Requirement: Constructor parameter renames do not spread to other classes
For a parameter of a Python `__init__` or `__new__`, the renamed declarations SHALL be the parameter named `old` of the
located `def` and of its overload group only, with or without `--no-in-hierarchy`. Call keywords SHALL follow the
checker: `A(old=...)`, `cls(old=...)` and `super().__init__(old=...)` resolving to a renamed declaration SHALL be
rewritten. A keyword of a call of a class declaring both `__init__` and `__new__` with a parameter `old` SHALL be
rewritten only when the run renames both to the same name. The same-named constructor parameter of a base, a subclass or a sibling class, its body uses and the
keywords of calls resolving to it SHALL be unchanged and SHALL NOT be listed. A TypeScript rename of a constructor
parameter SHALL likewise change no other class's constructor.

#### Scenario: Sibling constructors
- **WHEN** `class Base(Exception)` declares `__init__(self, msg: str)`, `class A(Base)` and `class B(Base)` each
  declare `__init__(self, msg: str, *, field: str)`, a module raises `A("x", field="a")` and `B("y", field="b")`, and
  `A.__init__`'s `field` is renamed to `column`
- **THEN** `A.__init__`'s parameter, its body uses and `A("x", column="a")` are renamed, and `B.__init__`, its body and
  `B("y", field="b")` are unchanged

#### Scenario: Subclass forwarding to the renamed constructor
- **WHEN** `class C(A)` declares `__init__(self, msg: str, *, field: str)` whose body calls
  `super().__init__(msg, field=field)`, and `A.__init__`'s `field` is renamed to `column`
- **THEN** the call becomes `super().__init__(msg, column=field)` and `C.__init__`'s own parameter is unchanged

#### Scenario: __new__ and an overloaded __init__
- **WHEN** sibling classes each declare `__new__(cls, *, field: str)`, and a class declares two `@overload` stubs and
  an implementation of `__init__` each with `field`, and one class's parameter is renamed in each
- **THEN** only the located class's declarations (every member of its overload group) and its calls are renamed

#### Scenario: Class declaring both constructors
- **WHEN** a class declares `__new__(cls, *, field: str)` and `__init__(self, *, field: str)`, a module calls
  `K(field="a")`, and `__init__`'s `field` is renamed
- **THEN** the call is listed as an unlinked keyword and the rename refuses; a `rename-map` renaming both parameters to
  `column` renames both declarations and the call

#### Scenario: Several constructors in one map
- **WHEN** a `rename-map` holds one entry for `A.__init__(field)` and one for `B.__init__(field)`
- **THEN** both constructors and both calls are renamed in one diff

#### Scenario: TypeScript sibling constructors
- **WHEN** TypeScript classes `A extends Base` and `B extends Base` each declare `constructor(msg: string, field:
  string)` and `A`'s `field` is renamed
- **THEN** only `A`'s constructor parameter and its uses change

## MODIFIED Requirements

### Requirement: Python parameter renames cover every parameter kind
The Python `dr-refactor rename` SHALL rename a `def` or `async def` parameter of any kind (positional-only,
positional-or-keyword, keyword-only, `*args`, `**kwargs`) located by `--line`/`--col`, `--offset` or `--symbol`, at
its declaration, at a use in its function or at a `name=` keyword of a call. It SHALL rewrite each renamed
declaration, every use of it in its function including nested scopes, and every `name=` keyword at a call the
checker resolves to a renamed declaration, links to one through the callee's signature, or carries to one through
`**kwargs` carriers, as the requirements on those links define. A `name=` keyword SHALL resolve only to a
positional-or-keyword or keyword-only parameter, never to a positional-only parameter, `*args` or `**kwargs`.
Positional arguments and the keys of a mapping unpacked by name (`f(**mapping)`) SHALL be unchanged, as SHALL every
other text those requirements do not name.

#### Scenario: Keyword-only parameter of a function
- **WHEN** `def kwonly(*, model_name: str) -> str: return model_name` has its parameter renamed to `dataset_name`,
  and a module elsewhere in the project calls `kwonly(model_name="x")`
- **THEN** the declaration, the body use and the call's keyword are renamed, and the exit code is 0

#### Scenario: Keyword-only parameter after *args
- **WHEN** `def star(*xs: int, model_name: str) -> str` has `model_name` renamed and a call is
  `star(1, 2, model_name="x")`
- **THEN** the declaration, its body uses and the keyword are renamed, and `1, 2` are unchanged

#### Scenario: Keyword-only parameter of a method through an annotated receiver
- **WHEN** `C.kmeth(self, *, model_name: str)` has `model_name` renamed and a function `use(c: C)` calls
  `c.kmeth(model_name="y")`
- **THEN** the declaration, its body uses and the keyword are renamed

#### Scenario: Async method keyword-only parameter
- **WHEN** `async def fetch(self, *, model_name: str)` of class `C` has `model_name` renamed and a function awaits
  `c.fetch(model_name="y")` with `c: C`
- **THEN** the declaration, its body uses and the keyword are renamed

#### Scenario: Positional-only parameter
- **WHEN** `def posonly(model_name: str, /) -> str: return model_name` has its parameter renamed and a call is
  `posonly("x")`
- **THEN** the declaration and the body use are renamed and the call is unchanged

#### Scenario: Located at a call keyword
- **WHEN** the rename locates `model_name` by `--line`/`--col` at the keyword of `kwonly(model_name="x")`
- **THEN** the declaration, the body use and every resolved keyword are renamed

#### Scenario: Located by path
- **WHEN** the rename locates it by `--symbol kwonly(model_name)`
- **THEN** the result equals the rename located at its declaration

#### Scenario: Mixed-kind signature
- **WHEN** `def f(a: int, /, b: int, *xs: int, c: int = 0, **kw: int) -> int` uses each parameter in its body, the
  project calls `f(1, 2, 3, c=4, d=5)`, `f(1, b=2)` and `f(1, 2, a=3)`, and `b` and then `c` are renamed
- **THEN** each rename changes its declaration, its body uses and its own keywords only (`b=2` for `b`, `c=4` for
  `c`); `a=3` and `d=5` are unchanged

#### Scenario: Keywords that do not bind the parameter are unchanged
- **WHEN** `def g(a: int, /, *args: int, **kwargs: int) -> None` has `a`, then `args`, then `kwargs` renamed, and the
  project calls `g(1, a=2, args=3, kwargs=4)`
- **THEN** each rename changes its declaration and body uses only, and every keyword of the call is unchanged

#### Scenario: Unresolved keyword sites are unchanged
- **WHEN** `kwonly`'s `model_name` is renamed and the project holds `kwonly(**mapping)` with `mapping` a parameter, and
  `functools.partial(kwonly, model_name="x")`
- **THEN** the `**mapping` site is unchanged, and the `functools.partial` keyword, which the checker resolves to
  `kwonly`, is renamed

#### Scenario: Keywords reaching the function indirectly
- **WHEN** `kwonly`'s `model_name` is renamed and the project holds `kwonly(**{"model_name": "x"})` and a wrapper
  `def wrap(**kw: str) -> str: return kwonly(**kw)` called as `wrap(model_name="x")`
- **THEN** the dict literal's key and the `wrap` keyword are renamed

#### Scenario: Other refactors over mixed-kind signatures
- **WHEN** a module holds `def f(a: A, /, *, b: A) -> None` whose body calls `a.get_model()` and `b.get_model()`,
  and method `A.get_model` is renamed, and separately `f` is moved to another module with `move-symbol`
- **THEN** the rename renames both calls, and the move rewrites `f`'s imports and calls exactly as for a function
  with positional-or-keyword parameters

### Requirement: Python method parameter renames follow the hierarchy
For a parameter of a method other than `__init__` and `__new__`, the renamed declarations SHALL be the parameters named `old` of every declaration in the
method's renamed hierarchy: the whole hierarchy by default, only the located method with `--no-in-hierarchy`. Calls
through annotated or inferred receivers and `super().m(old=...)` calls SHALL be rewritten for each renamed
declaration. An override whose parameter has another name, or that has no parameter named `old`, SHALL be unchanged.
This SHALL hold for instance methods, `@classmethod`, `@staticmethod` and `async def` methods, for every parameter kind
of the previous requirement.

#### Scenario: Keyword-only parameter across an override
- **WHEN** `A.run(self, *, model_name: str)` is overridden by `B(A).run(self, *, model_name: str)` whose body returns
  `super().run(model_name=model_name)`, and a function holds `a.run(model_name="x")` with `a: A` and
  `b.run(model_name="y")` with `b: B`, and `A.run`'s `model_name` is renamed
- **THEN** both declarations, both bodies, the `super()` keyword and both calls' keywords are renamed

#### Scenario: Located at the override
- **WHEN** the same project renames `B.run`'s `model_name`
- **THEN** the same edits are made as when located at `A.run`

#### Scenario: Hierarchy off
- **WHEN** the same project renames `A.run`'s `model_name` with `--no-in-hierarchy`
- **THEN** only `A.run`'s declaration and body, the `super()` call's keyword and `a.run(...)`'s keyword are renamed;
  `B.run`'s declaration and body and `b.run(...)` are unchanged

#### Scenario: Positional-or-keyword parameter across an override
- **WHEN** `A.run(self, model_name: str)` is overridden by `B.run(self, model_name: str)` and the project calls
  `a.run(model_name="x")`, `b.run(model_name="y")` and `a.run("z")`, and `A.run`'s `model_name` is renamed
- **THEN** both declarations, both bodies and both keywords are renamed, and `a.run("z")` is unchanged

#### Scenario: Override with another parameter name
- **WHEN** `A.run(self, *, model_name: str)` is overridden by `B.run(self, *, name: str)` and `A.run`'s `model_name`
  is renamed
- **THEN** `B.run` is unchanged

#### Scenario: Class, static and async methods
- **WHEN** a classmethod, a staticmethod and an `async def` method of `A`, each overridden in `B(A)` and each with a
  keyword-only `model_name`, have `model_name` renamed in turn, with calls `A.cm(model_name=...)`,
  `A.sm(model_name=...)` and `await b.am(model_name=...)`
- **THEN** each rename changes both declarations, both bodies and the call's keyword

### Requirement: Python --attr reports Unknown and Any receivers
Python `dr-compliance --attr NAME` SHALL report, as the `attr-blindspot` check, every access `x.NAME` whose receiver
basedpyright types as `Unknown`, `Any`, `Never`, or a union containing one of them, and every Python string-member form of the
language registry whose member argument is the plain string literal `NAME` and whose object argument is typed so or
whose callee basedpyright cannot resolve while the call has the form's syntax, with the shared
`compliance.attr-blindspot` finding: `{receiver}` SHALL be the receiver's (or object argument's) source text, with
the parentheses written around it and each run of whitespace collapsed to one space, and `{type}` SHALL be `Unknown`
when the type is or holds `Unknown` and for an unresolved callee, else `Any` when it is or holds `Any`, else `Never`. Findings SHALL be one per access or call position, sorted by path, line and column.
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

#### Scenario: Receiver the checker types Never
- **WHEN** `--attr producer_root_model` runs on a file holding `def roots(planned):` with
  `attaches = list(getattr(planned, "attach_plans", ()) or ())` and `for a in attaches: a.producer_root_model`, where
  the checker types `a` as `Never`
- **THEN** the access is reported with receiver `a` and `{type}` `Never`, and the exit code is 1

#### Scenario: Never through a comprehension and a subscript
- **WHEN** the same file holds `[k.producer_root_model for k in list(g)]` and `list(g)[0].producer_root_model` with
  `g = getattr(planned, "attach_plans", ())`
- **THEN** both accesses are reported

#### Scenario: Parenthesised receiver
- **WHEN** a file holds `(g or planned).formula` with both names untyped
- **THEN** the access is reported with receiver `(g or planned)`

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

### Requirement: Member renames refuse on untyped receivers
A member rename SHALL be a `dr-refactor rename` whose symbol is declared in a class body: in Python a method (sync
or async), property, class attribute, instance attribute (`self.x`) or field; in TypeScript a property, method or
accessor of a class, interface or type literal. A blind spot of the old name OLD SHALL be, in a source file of the
rename's language under the project:
- an attribute access `x.OLD` (in TypeScript also `x['OLD']`, the element a plain string literal) whose receiver
  the checker types as unknown (Python `Unknown`, `Any`, `Never` or a union holding one of them; TypeScript `any`);
- a string-member form whose object argument is typed so, or whose callee the checker cannot resolve while the call
  has the form's syntax (the form's attribute path and the member argument a plain string literal exactly OLD);
- a Python dotted patch target whose first segment names a project top-level package, one of whose segments is
  OLD, and that does not resolve statically to exactly one declaration, or whose call has a target form's syntax
  while its callee does not resolve.

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
- **THEN** the call is a blind spot and the rename refuses

#### Scenario: Never receiver refuses the rename
- **WHEN** field `Attach.producer_root_model` is renamed and a function reads `a.producer_root_model` in
  `for a in list(getattr(planned, "attach_plans", ()) or ())` with `planned` unannotated
- **THEN** stderr ends with the `attr-blindspot` line for `a.producer_root_model` with `{type}` `Never` followed by
  `refactor.blindspots`, the exit code is 1 and no file changes

#### Scenario: Non-member renames are not scanned
- **WHEN** a module-level function or a parameter is renamed while untyped `x.old` accesses exist
- **THEN** no access is reported as a blind spot; a parameter rename is scanned for unlinked keywords only

#### Scenario: TypeScript any receiver
- **WHEN** property `Store.getModel` is renamed in TypeScript and a file holds `function g(o: any) { return o.getModel() }`
- **THEN** the rename refuses with that site's `attr-blindspot` line, `{type}` `any`

#### Scenario: TypeScript element access on an any receiver
- **WHEN** property `Store.getModel` is renamed and a file holds `function g(o: any) { return o['getModel']('a') }`
- **THEN** the rename refuses with that site's `attr-blindspot` line, and `dr-compliance --select attr-blindspot
  --attr getModel` reports the same line

#### Scenario: Virtualenv skipped by both
- **WHEN** a Python member rename's project holds `.venv/lib/x.py` with an untyped `o.OLD`
- **THEN** neither the rename nor `dr-compliance --select attr-blindspot --attr OLD <project>` reports it

### Requirement: Python --unsure include renames unresolved receivers
With `--unsure include`, a Python rename SHALL also rename every access `x.OLD` whose receiver the checker types as
`Unknown`, `Any`, `Never` or a union holding one of them, and every unlinked keyword, and SHALL print the `refactor.unsure-warning` finding on stdout before the
diff. Blind spots SHALL be reported, refused and let through by `--allow-blindspots` as without it. With the default
`--unsure skip` no such access SHALL be renamed.

#### Scenario: Untyped receiver renamed on request
- **WHEN** method `A.run` is renamed with `--unsure include --allow-blindspots` and a module holds `def f(o): o.run()`
- **THEN** `o.run()` becomes `o.<new>()`, stdout starts with the `refactor.unsure-warning` line, and the blind spot is
  listed on stderr

#### Scenario: Skipped by default
- **WHEN** the same rename runs with `--allow-blindspots` only
- **THEN** `o.run()` is unchanged and the blind spot is listed on stderr
