## ADDED Requirements

### Requirement: Python renames reach names bound by tuple targets
The Python `dr-refactor rename` and `rename-map` SHALL rename a name bound by a tuple target, located by `--symbol`
or by location at any of its occurrences: a target of an assignment in a function, at module level or in a class
body, a starred target and a target nested in an inner tuple included, or a target of a comprehension's `for`
clause. They SHALL rewrite every reference bound to that declaration. A same-spelled binding in a nested scope (an
inner function or comprehension) SHALL NOT be renamed, and a `name=` keyword of a call SHALL NOT be renamed with a
same-named variable of the enclosing scope.

#### Scenario: Function local by symbol
- **WHEN** `def f(s):` holds `a, model_name = s.split(".", 1)` and `return model_name`, and `rename --symbol
  'f.<locals>.model_name' --new-name dataset_name` runs
- **THEN** both occurrences become `dataset_name` and the exit code is 0

#### Scenario: Function local by location
- **WHEN** the same rename is located by `--line`/`--col` at the tuple target
- **THEN** the result equals the rename by `--symbol`

#### Scenario: Module level
- **WHEN** a module has `ds_name, model_name = "a.b".split(".", 1)` and `print(model_name)`, and `--symbol
  model_name` is renamed
- **THEN** both occurrences are renamed

#### Scenario: Class body
- **WHEN** `class C:` holds `x, y = 1, 2` and the module reads `C.y`, and `--symbol C.y` is renamed
- **THEN** the target and `C.y` are renamed

#### Scenario: Starred target
- **WHEN** a function holds `a, *rest = s` and `return rest`, and `rest` is renamed
- **THEN** both occurrences are renamed and the `*` stays

#### Scenario: Nested tuple target
- **WHEN** a function holds `(a, b), c = s` and returns `b` and `c`, and `c`, then `b`, is renamed
- **THEN** each rename rewrites that target and its use, and nothing else

#### Scenario: Await right-hand side
- **WHEN** `async def g(s):` holds `_scopes, ds_by_model = await scopes(s)` and `return ds_by_model`, and
  `g.<locals>.ds_by_model` is renamed
- **THEN** both occurrences are renamed

#### Scenario: Comprehension target
- **WHEN** `[model for model, measure in chain]` has `model` renamed, located at its target
- **THEN** both occurrences of `model` are renamed and `measure` is unchanged

#### Scenario: Nested-scope binding of the same spelling
- **WHEN** a function holds `a, model_name = s` and `return [model_name for model_name in xs], model_name`, and the
  tuple-bound `model_name` is renamed
- **THEN** the target and the last `model_name` are renamed, and the comprehension is unchanged

#### Scenario: Call keyword of the same spelling
- **WHEN** `def h():` holds `a, x = 1, 5` and `return g(x=1) + x`, where `def g(x=0)`, and the local `x` is renamed
- **THEN** the target and `+ x` are renamed, and `g(x=1)` is unchanged

#### Scenario: Rename map of tuple targets
- **WHEN** a `rename-map` lists tuple-bound names in a function, at module level, in a class body and in a nested
  target, by `symbol` and by `line`/`col`
- **THEN** one diff renames every entry, as the separate renames would, and the exit code is 0

## MODIFIED Requirements

### Requirement: Python moves rewrite each reference minimally
For a Python `move-module` or `move-symbol`, each occurrence of the moved module or symbol SHALL be handled by
exactly one rule, decided from the objects its names resolve to:
1. An import statement naming the old path (absolute or relative, at any scope, including `from old import *` and
   package-prefixed paths) SHALL have its path rewritten in place, keeping its alias, bound names, comments and layout.
   A relative import SHALL stay relative, recomputed from the importer's new location and the target's new location.
   It SHALL become absolute only when the target cannot be reached relatively. A relative import between files that
   move together SHALL be unchanged. In a `from` import where exactly one name moves, that name SHALL be removed in
   place, and the moved name SHALL get a new `from` statement, with its alias, on the line after the statement ends,
   at the same indentation.
2. A use whose binding still resolves after the move SHALL be unchanged. Such a binding is a name bound by a rule-1
   import, a name another module binds explicitly (by import or assignment), or a name the function, lambda or
   comprehension scope the use is read in binds by anything other than a rule-1 import (a parameter of any kind, an
   assignment, a comprehension target), even when that scope also imports it. A name a `global` or `nonlocal`
   statement declares SHALL resolve in the scope the statement names, and a comprehension's first iterable SHALL
   resolve in the enclosing scope.
3. A use whose binding no longer resolves after the move SHALL be rewritten. Such a use reaches a submodule only as a
   package attribute, or reaches the moved symbol through its old module or a star import of it. A dotted use SHALL
   become the new dotted path, and `import <new module>` SHALL be added on the line after the import binding the
   chain's root. A bare name bound by a star import SHALL stay as it is, and `from <new module> import <name>` SHALL be
   added on the line after the star import. No import SHALL be added where that scope already binds the same object.
An import binding SHALL be removed in place only when every use of it was rewritten by this refactor, and no `nonlocal`
statement names it. For
`move-symbol`, an import of the source module SHALL also be removed in place when every use of it lay in the moved
code. In the source module, a `__all__` entry naming the moved symbol SHALL be removed, and a remaining use of the
symbol (by rule 2, not a use a function, lambda or comprehension scope binds) SHALL get `from <dest> import <name>` after the leading import block. In the destination, the imports the moved
code needs SHALL be added after the leading import block. An import of the symbol from the source SHALL be removed in
place, and each use of a name it bound under an alias SHALL become the symbol's name. The leading import block is the
first contiguous run of import statements, ending at the first non-import statement; in a file without imports it is
the position after the module docstring and `__future__` imports. Edits
SHALL be located by source character, so non-ASCII text before them on the line does not shift them. When an
added import or the moved code would bind a name that already resolves to a different object in that scope,
`dr-refactor` SHALL exit 1 with the name-conflict finding naming the file and line, and SHALL write nothing.

#### Scenario: Multi-name from-import split in place
- **WHEN** `move-module` moves `pkg/sql/client.py` to `pkg/database` and a file has
  `from pkg.sql import dialects, client` between `import sys` and `import os`
- **THEN** that line becomes `from pkg.sql import dialects`, the next line is `from pkg.database import client`, and
  every other line is byte-identical

#### Scenario: Parenthesized from-import with per-name comments
- **WHEN** the moved name sits on its own line, with a comment, inside a parenthesized multi-line `from` import with a
  trailing comma
- **THEN** only that line is removed, the other names and their comments stay, and the new statement follows the
  closing parenthesis

#### Scenario: Function-local import rewritten in place
- **WHEN** a function body holds `from pkg.sql import client  # ALLOW(import-not-top)` and uses `client.X`
- **THEN** only that import's module path changes, the use is untouched, and no module-level import is added

#### Scenario: Use through another module untouched
- **WHEN** a file uses `sql_client.engine_factory`, and `sql_client` is a module that imports the moved
  `engine_factory` by name
- **THEN** the use is unchanged and no import is added to the file

#### Scenario: Self-aliased import
- **WHEN** `move-module` moves `pkg/a/mod.py` to `pkg/b` and a file has `import pkg.a.mod as mod` and `print(mod.X)`
- **THEN** the import becomes `import pkg.b.mod as mod`, the use is unchanged, and the command exits 0

#### Scenario: Dotted use through the moved module's own import
- **WHEN** a file has `import pkg.sql.client` and uses `pkg.sql.client.X`
- **THEN** they become `import pkg.database.client` and `pkg.database.client.X`, and no import is added

#### Scenario: Use through a package attribute
- **WHEN** a file has `import pkg.sql as sql_pkg` and uses `sql_pkg.client.X`, and `pkg/sql/__init__.py` does not
  import `client`
- **THEN** the use becomes `pkg.database.client.X` and `import pkg.database.client` is added on the line after
  `import pkg.sql as sql_pkg`

#### Scenario: Symbol reached through a module alias
- **WHEN** `move-symbol` moves `f` from `pkg/a.py` to `pkg/b.py` and a file has `import pkg.a as pa` used only as
  `pa.f()`
- **THEN** the use becomes `pkg.b.f()`, `import pkg.b` replaces `import pkg.a as pa` in place, and every other line
  is unchanged

#### Scenario: Old module import with another surviving use
- **WHEN** the file in the previous scenario also uses `pa.g()`
- **THEN** `import pkg.a as pa` stays, `pa.g()` is unchanged, and `import pkg.b` is added on the next line

#### Scenario: Star-import consumer
- **WHEN** `move-symbol` moves `f` out of `pkg/a.py` and a file has `from pkg.a import *` and calls `f()`
- **THEN** `from pkg.b import f` is added on the line after the star import, and the call is unchanged

#### Scenario: Re-export keeps exporting
- **WHEN** `pkg/__init__.py` has `from pkg.a import f as public_f` and `pkg/a.py`'s `__all__` lists `"f"`
- **THEN** the re-export becomes `from pkg.b import f as public_f`, and `"f"` is removed from `pkg/a.py`'s `__all__`

#### Scenario: Relative import stays relative
- **WHEN** `pkg/sql/engine.py` has `from . import client` and `pkg/sql/client.py` moves to `pkg/database`
- **THEN** the import becomes `from ..database import client`

#### Scenario: Moved module's own relative imports
- **WHEN** the moved `pkg/sql/client.py` has `from . import dialects`
- **THEN** in `pkg/database/client.py` it becomes `from ..sql import dialects`

#### Scenario: Package move keeps internal relative imports
- **WHEN** `move-module` moves package `pkg/sql` to `pkg/database` and `pkg/sql/client.py` has `from .dialects import D`
- **THEN** that line is unchanged in `pkg/database/sql/client.py`

#### Scenario: Move across top-level packages
- **WHEN** a relative import's target moves to another top-level package
- **THEN** the import becomes absolute

#### Scenario: Import edit forms
- **WHEN** an import of the moved module is backslash-continued, follows a semicolon on its line, or sits in a file
  with CRLF line endings, no final newline, or non-ASCII text earlier on the line
- **THEN** only the module path changes, and line endings, the final-newline state and the other statement are
  preserved

#### Scenario: Destination imports added without reflow
- **WHEN** `move-symbol` moves `f`, which uses `os`, into a destination whose import block is unsorted and gated by
  `importorskip`
- **THEN** `import os` is added after the destination's leading import block, and no existing line moves

#### Scenario: Destination already binds the needed module
- **WHEN** the destination already has `import os`
- **THEN** no import is added

#### Scenario: Name conflict refused
- **WHEN** `move-symbol` moves `f`, which uses module `os`, into a destination where `os` is assigned another value
  or bound by an aliased import of another module; or a function-local `import pkg.a as pa`, whose `pa.f()` needs
  `import pkg.b`, sits in a function where `pkg` is a parameter or is bound by an enclosing function
- **THEN** it exits 1 with the name-conflict finding naming that file and the existing binding's line, and no file
  changes

#### Scenario: Parameters shadowing an import alias
- **WHEN** `move-module` moves `pkg/sub/thing.py` to `pkg`, and a file with `import pkg.sub as sub` and
  `print(sub.thing.X)` also reads `sub.thing.X` in `lambda sub: …`, in a function whose positional-only,
  positional-or-keyword, keyword-only, `*sub` or `**sub` parameter is `sub`, and in a comprehension whose target is
  `sub`
- **THEN** `print(sub.thing.X)` becomes `print(pkg.thing.X)` and every shadowed use is unchanged

#### Scenario: Function-local import of the alias rewritten
- **WHEN** a function body holds `import pkg.sub as sub` and reads `sub.thing.X`, and `pkg/sub/thing.py` moves to `pkg`
- **THEN** the use is rewritten like a module-level one

#### Scenario: Function scope that also assigns the alias
- **WHEN** a function body holds `import pkg.sub as sub`, reads `sub.thing.X`, and assigns `sub = None`
- **THEN** the use is unchanged

#### Scenario: global and nonlocal declarations
- **WHEN** a function declares `global sub` and reads `sub.thing.X`, where `sub` is the module's `import pkg.sub as
  sub`; and an inner function declares `nonlocal sub` and reads `sub.thing.X`, where `sub` is its enclosing
  function's `import pkg.sub as sub`
- **THEN** both uses are rewritten

#### Scenario: nonlocal keeps the enclosing import
- **WHEN** an inner function declares `nonlocal sub` and reads `sub.thing.X`, and that is the only use of its enclosing
  function's `import pkg.sub as sub`
- **THEN** the use is rewritten, the import stays, and `import pkg.thing` is added on the line after it

#### Scenario: Comprehension's first iterable
- **WHEN** a file with `import pkg.sub as sub` has `[sub for sub in sub.thing.ITEMS]`
- **THEN** the iterable becomes `pkg.thing.ITEMS` and the target and element are unchanged

#### Scenario: Defaults and annotations read the enclosing scope
- **WHEN** a file with `import pkg.sub as sub` has `def f(sub: int = sub.thing.X): return sub`
- **THEN** the default becomes `pkg.thing.X` and the body's `sub` is unchanged

#### Scenario: Moved symbol shadowed in its source module
- **WHEN** `move-symbol` moves `f` out of `pkg/a.py`, whose only other reads of `f` are `lambda f: f()` and a
  function with keyword-only parameter `f`
- **THEN** those reads are unchanged and no `from <dest> import f` is added to `pkg/a.py`

#### Scenario: Star-import consumer shadowing the moved name
- **WHEN** `move-symbol` moves `f` out of `pkg/a.py`, and a file with `from pkg.a import *` reads `f` only in
  `lambda f: f()`
- **THEN** that file is unchanged
