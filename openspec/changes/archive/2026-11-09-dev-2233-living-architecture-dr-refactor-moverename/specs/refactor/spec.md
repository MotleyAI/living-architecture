## ADDED Requirements

### Requirement: Refactors edit only at references
In both languages, a file that `dr-refactor` touches SHALL change only within these permitted regions: the span of each
resolved reference to the renamed or moved module or symbol; the import item holding such a reference (its whole
statement, or its whole line, when it is the statement's only item); one inserted import statement directly after a
referencing import statement or after the leading import block; and, for `move-symbol`, the moved code's region.
Every other byte SHALL be unchanged: no import SHALL be reordered, merged, hoisted or reformatted, and no
non-import statement SHALL move. A `from` import SHALL be split only when exactly one of its names moves. CRLF line
endings and a missing final newline SHALL be preserved.

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
   import, or a name another module binds explicitly (by import or assignment).
3. A use whose binding no longer resolves after the move SHALL be rewritten. Such a use reaches a submodule only as a
   package attribute, or reaches the moved symbol through its old module or a star import of it. A dotted use SHALL
   become the new dotted path, and `import <new module>` SHALL be added on the line after the import binding the
   chain's root. A bare name bound by a star import SHALL stay as it is, and `from <new module> import <name>` SHALL be
   added on the line after the star import. No import SHALL be added where that scope already binds the same object.
An import binding SHALL be removed in place only when every use of it was rewritten by this refactor. For
`move-symbol`, an import of the source module SHALL also be removed in place when every use of it lay in the moved
code. In the source module, a `__all__` entry naming the moved symbol SHALL be removed, and a remaining use of the
symbol SHALL get `from <dest> import <name>` after the leading import block. In the destination, the imports the moved
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
