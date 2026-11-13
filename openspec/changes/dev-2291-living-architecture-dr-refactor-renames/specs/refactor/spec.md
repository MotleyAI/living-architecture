## ADDED Requirements

### Requirement: Python parameter renames cover every parameter kind
The Python `dr-refactor rename` SHALL rename a `def` or `async def` parameter of any kind (positional-only,
positional-or-keyword, keyword-only, `*args`, `**kwargs`) located by `--line`/`--col`, `--offset` or `--name`, at its
declaration, at a use in its function or at a `name=` keyword of a call. It SHALL rewrite each renamed declaration,
every use of it in its function including nested scopes, and every `name=` keyword at a call the checker resolves to
a renamed declaration. A `name=` keyword SHALL resolve only to a positional-or-keyword or keyword-only parameter, never
to a positional-only parameter, `*args` or `**kwargs`. Positional arguments, keywords that reach the function
unresolved (`**mapping` unpacking, `**kwargs` forwarding, `functools.partial`) and every other text SHALL be unchanged.

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
- **WHEN** `kwonly`'s `model_name` is renamed and the project holds `kwonly(**{"model_name": "x"})`, a wrapper
  `def wrap(**kw: str) -> str: return kwonly(**kw)` called as `wrap(model_name="x")`, and
  `functools.partial(kwonly, model_name="x")`
- **THEN** none of those three is changed

#### Scenario: Other refactors over mixed-kind signatures
- **WHEN** a module holds `def f(a: A, /, *, b: A) -> None` whose body calls `a.get_model()` and `b.get_model()`,
  and method `A.get_model` is renamed, and separately `f` is moved to another module with `move-symbol`
- **THEN** the rename renames both calls, and the move rewrites `f`'s imports and calls exactly as for a function
  with positional-or-keyword parameters

### Requirement: Python method parameter renames follow the hierarchy
For a parameter of a method, the renamed declarations SHALL be the parameters named `old` of every declaration in the
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

### Requirement: Python parameter renames follow the overload group
A function's overload group SHALL be every same-named `def` of one module or class body when at least one of them is
decorated with a decorator the checker resolves to `typing.overload` or `typing_extensions.overload`, however it is
imported or aliased. For each renamed declaration that belongs to an overload group, the parameter named `old` of every
member of the group SHALL be renamed, with or without `--no-in-hierarchy`, whichever member the locator names. A
method's hierarchy SHALL be computed from its group's implementation, or from the located `def` when the group has no
implementation. Calls the checker resolves to any member SHALL have their `old=` keyword rewritten.

#### Scenario: Located at the implementation
- **WHEN** a module holds two `@overload` stubs `def f(*, model_name: str) -> str: ...` and
  `def f(*, model_name: int) -> int: ...`, the implementation `def f(*, model_name: str | int) -> str | int`, and a
  call `f(model_name="x")`, and the implementation's `model_name` is renamed
- **THEN** the parameter of both stubs and of the implementation, the implementation's body and the call's keyword are
  renamed

#### Scenario: Located at a stub
- **WHEN** the same module's first stub's `model_name` is renamed, and separately the second stub's
- **THEN** each rename makes the same edits as the rename located at the implementation

#### Scenario: Aliased overload decorator
- **WHEN** the module imports `from typing import overload as ov` and decorates the stubs with `@ov`
- **THEN** the rename makes the same edits as with `@overload`

#### Scenario: Overloaded method in a hierarchy
- **WHEN** `A.run` has two `@overload` stubs and an implementation, each with a keyword-only `model_name`, `B(A)`
  overrides `run` with a plain method, and `A.run`'s implementation parameter is renamed
- **THEN** every stub, both implementations and every resolved call keyword are renamed; with `--no-in-hierarchy` the
  stubs and `A.run` are renamed and `B.run` is unchanged

### Requirement: Python parameter renames refuse a name the function already uses
A parameter rename SHALL be refused when the function of any renamed declaration already binds or reads the new name
as a variable in its signature or its body, nested scopes included, at a site the rename does not itself rewrite.
`dr-refactor` SHALL then print the `refactor.name-conflict` finding naming the first such site by project-relative path
and then by character offset, with its file and line, write nothing and exit 1. Attribute names (`x.new`) and keywords
of calls to other functions SHALL NOT count. A rename to the old name SHALL succeed as a rename with no edits.

#### Scenario: Duplicate parameter
- **WHEN** `def g(*, model_name: str, dataset_name: str) -> str` has `model_name` renamed to `dataset_name`
- **THEN** stderr is the `refactor.name-conflict` finding naming `dataset_name`, the file and the line of `g`'s
  `dataset_name` parameter, the exit code is 1 and no file changes

#### Scenario: Body reads a global of the new name
- **WHEN** the module defines `dataset_name = "d"`, and `def h(*, model_name: str) -> str: return dataset_name +
  model_name` has `model_name` renamed to `dataset_name`
- **THEN** the rename is refused with `refactor.name-conflict` naming the line of the read

#### Scenario: Body assigns a local of the new name
- **WHEN** `def k(*, model_name: str) -> str` assigns `dataset_name = model_name.upper()` and returns it, and
  `model_name` is renamed to `dataset_name`
- **THEN** the rename is refused with `refactor.name-conflict` naming the line of the assignment

#### Scenario: Conflict in an override
- **WHEN** `A.run(self, *, model_name: str)` is clean and its override `B.run` reads a global `dataset_name`, and
  `A.run`'s `model_name` is renamed to `dataset_name`
- **THEN** the rename is refused with `refactor.name-conflict` naming `B.run`'s file and the line of the read

#### Scenario: First conflict is reported
- **WHEN** the base method's body and its override's body in another module each read `dataset_name`, the override's
  body twice, and the rename to `dataset_name` runs
- **THEN** the finding names the conflict in the file whose project-relative path sorts first, and within it the
  earliest by character offset

#### Scenario: Attributes and other calls' keywords are not conflicts
- **WHEN** `def m(*, model_name: str, o: O) -> str` reads `o.dataset_name` and calls `other(dataset_name=1)`, and
  `model_name` is renamed to `dataset_name`
- **THEN** the rename proceeds and those two sites are unchanged

#### Scenario: Rename to the same name
- **WHEN** a keyword-only parameter of a method with an override and of a function with an overload group is renamed
  to its own name
- **THEN** each rename exits 0 and no file changes

### Requirement: Python lambda parameters are refused
A rename located at a lambda parameter of any kind SHALL print the `refactor.cannot-rename` finding on stderr, write
nothing and exit 1.

#### Scenario: Keyword-only lambda parameter
- **WHEN** a module holds `f = lambda a, *, model_name: model_name` and the rename locates `model_name` in the
  lambda's parameters
- **THEN** stderr is the `refactor.cannot-rename` finding, the exit code is 1 and no file changes
