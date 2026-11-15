## MODIFIED Requirements

### Requirement: Python refactors walk every source construct
The Python `dr-refactor` SHALL compute every refactor over modules that rope's source walker fully covers. Every
syntax node SHALL be walked, except expression contexts, operators, `with` items and the internals of f-strings
and t-strings. Every string literal SHALL be covered over its full source text, including every piece of an
implicit concatenation and any `r`/`b`/`u`/`f`/`t` prefix in any order and case; covering surrounding parentheses
as well is allowed. This SHALL hold for every construct of the Python versions the package supports. The
following SHALL be refactored like any other code:
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
