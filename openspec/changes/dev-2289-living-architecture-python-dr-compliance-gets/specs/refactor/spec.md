## MODIFIED Requirements

### Requirement: Compliance check sets are per language
Each language's `dr-compliance` checks SHALL be listed in the language registry. Without `--select`, every
check of each file's language SHALL run. A selected id that no language lists SHALL exit 2; a selected id that
only another language lists SHALL not apply to a file. Python's checks SHALL be `untyped-def`,
`unannotated-attr`, `explicit-any`, `mock` and `rope-walk`. On files rope's walker fully covers and that reference
no `Any`, Python's output SHALL be unchanged.

#### Scenario: Python default unchanged
- **WHEN** `dr-compliance pkg` runs without `--select` in a Python repo whose files rope's walker fully covers and
  reference no `Any`
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

## ADDED Requirements

### Requirement: Python explicit-any compliance check
The Python `dr-compliance` check `explicit-any` SHALL report one `compliance.explicit-any` finding, at its line,
for every reference in the file that resolves to `typing.Any` or `typing_extensions.Any`, in any expression:
annotations at any depth, casts, type variable bounds, alias values, generic calls and class bases. Two
references on one line SHALL give two findings. The finding SHALL use the language's spellings of the any type
and the safe top type, `Any` and `object` for Python; the TypeScript `explicit-any` output SHALL be unchanged.

Resolution SHALL use the source alone, never importing or executing it:
- A name resolves to `Any` when every binding of it in the scope that resolves it, under Python's scoping rules
  (function, class, comprehension, `global`, `nonlocal`, except-handler and match bindings), imports `Any`;
  statement order within the scope SHALL NOT matter. Any other binding in that scope SHALL leave it unreported.
- `M.Any` resolves when `M` is bound to the module `typing` or `typing_extensions`, by `import` with or without
  `as`, or spelled in full (`typing.Any`). The names `typing` and `typing_extensions` SHALL always mean those
  modules, even when a first-party module has the same name.
- A name imported from a first-party module resolves when that module's binding of it resolves to `Any`,
  followed through chains of first-party modules; a cycle SHALL end the chain unresolved. A first-party module
  is one found under the importing file's import root, the parent of the topmost `__init__.py` package chain
  above the file: `a.b` is `<root>/a/b.py` or `<root>/a/b/__init__.py`, whether or not each directory has an
  `__init__.py`, and a relative import resolves against the file's own package. `from M import *` binds the
  names of a literal `__all__` in `M` when it has one, else every name of `M` without a leading underscore.
  A module that is neither first-party nor `typing` / `typing_extensions` SHALL never resolve to `Any`.
- An alias SHALL NOT be followed: the finding is where `Any` itself is written.

A string SHALL be read as a type expression only where it is a forward reference: a whole annotation, or an
element of a type expression's subscript, but never an argument of `Literal[...]` nor `Annotated[...]` metadata
after its first argument. A `# type:` comment SHALL be read as a type expression, and a function signature
comment as a signature; `# type: ignore` and a comment that does not parse SHALL be skipped. The statement that
imports `Any`, including a re-export such as `from typing import Any as Any`, SHALL NOT be reported. A file that
does not parse SHALL get only its `parse-error` finding.

#### Scenario: Nested and variadic annotations
- **WHEN** `--select explicit-any` runs on `def f(a: dict[str, Any], **kw: Any) -> list[Any]: ...`
- **THEN** three findings for that line are printed, the exit code is 1, and each reads
  ``<path>:<line>: explicit-any: an `Any` type — use a real type or `object` ``

#### Scenario: Every spelling of Any
- **WHEN** the file uses `Any` imported `from typing`, `X` imported as `from typing import Any as X`,
  `t.Any` after `import typing as t`, `typing.Any` after `import typing`, `typing_extensions.Any`, and `Any`
  after `from typing import *`
- **THEN** each use is reported once, and no import line is reported

#### Scenario: Expressions outside annotations
- **WHEN** the file has `cast(Any, x)`, `TypeVar("T", bound=Any)`, `Alias = dict[str, Any]`, `list[Any]()` and
  `class C(Base[Any])`
- **THEN** each `Any` is reported once

#### Scenario: Aliases are not followed
- **WHEN** the file has `A = Any` on line 3 and `x: A` on line 4
- **THEN** only line 3 is reported

#### Scenario: Forward references and type comments
- **WHEN** the file has `x: "dict[str, Any]"`, `y: list["Any"]`, `z = []  # type: list[Any]` and a function
  with `# type: (Any, int) -> Any`
- **THEN** each `Any` in them is reported once

#### Scenario: Strings that are not forward references
- **WHEN** the file has `x: Literal["Any"]`, `y: Annotated[int, "Any"]`, `# type: ignore` and a `# type:`
  comment that does not parse
- **THEN** nothing is reported for them and no error is printed

#### Scenario: Shadowed and mixed bindings
- **WHEN** a function has a parameter or local named `Any`, a module binds `Any` both by `from typing import Any`
  and by `Any = object`, or `t` is rebound after `import typing as t`
- **THEN** the uses resolving through those bindings are not reported

#### Scenario: Scoping
- **WHEN** a class body of a module that does not bind `Any` imports `Any`, and a method of that class uses `Any`
  in a parameter annotation and in its body; a function declares `global Any` for a module-level
  `from typing import Any`; and both branches of a `try`/`except ImportError` import `Any` from `typing` and
  `typing_extensions`
- **THEN** the parameter annotation is reported and the body's use is not, and the `global` use and the uses after
  the `try` are reported

#### Scenario: First-party re-exports
- **WHEN** `pkg/compat.py` has `from typing import Any as Any`, `pkg/__init__.py` has `from .compat import *`,
  and `pkg/a.py` uses `Any` imported from `pkg.compat`, `X` from `pkg` via `from pkg import Any as X`, and
  `c.Any` after `import pkg.compat as c`
- **THEN** each use in `pkg/a.py` is reported, and nothing is reported in `pkg/compat.py` or `pkg/__init__.py`

#### Scenario: Star import honours __all__ and private names
- **WHEN** `pkg/compat.py` binds `Any` and `_Any` to `typing.Any` with `__all__ = ["_Any"]`, and `pkg/a.py` does
  `from pkg.compat import *` and uses `Any` and `_Any`
- **THEN** only the use of `_Any` is reported

#### Scenario: Re-export cycle
- **WHEN** `pkg/a.py` imports `Any` from `pkg.b` and `pkg/b.py` imports `Any` from `pkg.a`
- **THEN** nothing is reported and the command does not hang

#### Scenario: Modules that are not first-party
- **WHEN** a file imports `Any` from a third-party package or from an unresolvable module, and the project holds
  its own `typing.py` that binds `Any = int`
- **THEN** the third-party and unresolvable `Any` are not reported, and `from typing import Any` still is

#### Scenario: Parse error only
- **WHEN** `dr-compliance` runs on a `.py` file that uses `Any` and has a syntax error
- **THEN** only its `parse-error` finding is printed
