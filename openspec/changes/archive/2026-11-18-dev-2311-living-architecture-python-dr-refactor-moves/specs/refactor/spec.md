## ADDED Requirements

### Requirement: Python moves resolve statically without rope
A Python `move-symbol` or `move-module` SHALL locate the moved symbol or module and resolve every occurrence of its name
by Python's scoping rules over the project's own modules, without importing or running them. It SHALL start no language
server, and rope SHALL compute no part of it: no reference, no region, no import and no edit. rope's only remaining part
in a move SHALL be the walker-gap check of its `checks` phase. Output SHALL be byte-identical to the output before this
change on every input that move-symbol's locator rules accept and where that output was valid Python that kept every
reference bound. A move whose source module's name more than one file of the project holds SHALL exit 1 with the
ambiguous-module finding naming the module and its files, and write nothing. When a file's declared encoding cannot hold
the text a move gives it, the move SHALL exit 1 with the unencodable finding naming the file and the encoding, and write
nothing.

#### Scenario: No server for a symbol move
- **WHEN** `move-symbol` runs, with or without `--apply`
- **THEN** no language server starts

#### Scenario: rope computes nothing
- **WHEN** `move-symbol` or `move-module` runs and every rope entry point other than the walker-gap check fails if
  called
- **THEN** the run prints the same output as before this change and exits 0

#### Scenario: Existing goldens unchanged
- **WHEN** every Python `move-symbol` and `move-module` conformance case that existed before this change runs
- **THEN** its stdout, stderr, files and exit code equal its golden

#### Scenario: Use through a package that binds the module itself
- **WHEN** `move-module` moves `pkg/sql/client.py` to `pkg/database`, `pkg/sql/__init__.py` holds `from . import
  client` (at module level, or inside an `if` or `try` block) or defines a module-level `__getattr__`, and a file
  uses `sql_pkg.client.X` after `import pkg.sql as sql_pkg`
- **THEN** the use is unchanged and no import is added for it

#### Scenario: Use through a submodule attribute only
- **WHEN** the same move runs, `pkg/sql/__init__.py` binds no `client`, and a file has `import pkg.sql` and uses
  `pkg.sql.client.X`
- **THEN** the use becomes `pkg.database.client.X` and `import pkg.database.client` is added on the line after
  `import pkg.sql`

#### Scenario: Module name held twice
- **WHEN** source folders `src1` and `src2` both hold `pkg/a.py`, and `move-module` moves `src1/pkg/a.py`
- **THEN** it exits 1 with the ambiguous-module finding naming `pkg.a` and both files, and no file changes

#### Scenario: Destination encoding cannot hold the moved code
- **WHEN** `move-symbol` moves a function returning `"€"` into a destination declaring `# coding: ascii`
- **THEN** it exits 1 with the unencodable finding naming the destination and `ascii`, and no file changes

### Requirement: Python move-symbol moves one top-level declaration
`move-symbol` SHALL resolve its locator (`--symbol`, `--line`/`--col` or `--offset`) to a site on one top-level
declaration of `--file`, which is always the move's source. A site on an import binding or on a reference SHALL NOT be
followed to a declaration elsewhere. The declaration SHALL be movable when it is a top-level `def`, `async def` or `class`, with its decorators; a
top-level assignment or annotated assignment whose only target is that one name; or an `@overload` group: the
contiguous run of `@overload`-decorated definitions of the name and the one definition without `@overload` directly
after them, moved together. Anything else SHALL exit 1 with the not-movable finding naming `--file` and write nothing:
a method, a local, a parameter, a module, an assignment binding more than one name or sharing its line with another
statement, a name bound only inside an `if`, `try`, `for`, `while`, `with` or `match` block, a name the source module
binds more than once at top level other than as one overload group, an import binding, and a reference.

The moved region SHALL start at the line of the first decorator (else the declaration's first line), extended upward
over the directly preceding lines that start with `#` in their first column, stopping at the file's header (a shebang on
line 1, a coding declaration on line 1 or 2), and end at the declaration's last line, extended over the following lines
holding only whitespace. A variable's region SHALL be its logical line. The moved text SHALL be the region without its
trailing whitespace, followed by one line break. In the destination, the moved text SHALL follow the last top-level
import statement; in a destination without one, it SHALL follow the module docstring, else precede the first statement.
When a later top-level destination statement binds a name the moved code reads while it is being defined (a base, a
decorator, a default, a class-body expression), the moved text SHALL instead follow the last such statement. When the
destination imports the moved symbol from the source in a top-level statement outside any block, and a later destination
statement before the moved text's position reads the symbol while it runs, the moved text SHALL instead follow that
import statement, taking its place when the import is removed. A destination that does not parse SHALL exit 1 with the
unparsable finding naming it, and write nothing.

#### Scenario: Import binding or reference as the locator
- **WHEN** `pkg/use.py` has `from pkg.engine import Engine` and calls `Engine()` in a function, and `move-symbol --file
  pkg/use.py --dest pkg/dest.py` runs with `--symbol Engine`, or with `--line`/`--col` on `Engine()`
- **THEN** each exits 1 with the not-movable finding naming `pkg/use.py`, as the TypeScript twin does for an imported
  use, and no file changes

#### Scenario: Not movable
- **WHEN** the locator is on a method, a local variable, a parameter, a module name in an import, one name of
  `a, b = 1, 2`, `x = 1; y = 2`, a name bound only inside `if TYPE_CHECKING:`, or a name assigned twice at top level
- **THEN** each exits 1 with the not-movable finding naming `--file`, prints no traceback and changes no file

#### Scenario: Overload group moves as one
- **WHEN** `pkg/a.py` declares two `@overload` signatures of `f` followed by its implementation, and `f` is moved
- **THEN** the signatures and the implementation leave `pkg/a.py` and appear together, in their order, in the
  destination

#### Scenario: Decorated class with leading comments
- **WHEN** a moved class has two decorators, a comment line between them, and two `#` lines directly above the first
  decorator, preceded by a blank line
- **THEN** the comment lines, the decorators and the class move, the blank line above them stays, and the blank lines
  after the class leave with it

#### Scenario: Moved variable
- **WHEN** `X: Final = (1,\n    2)` is moved
- **THEN** both physical lines of the statement move and nothing else

#### Scenario: File header stays in the source
- **WHEN** `pkg/a.py` starts with `#!/usr/bin/env python` and `# -*- coding: utf-8 -*-`, followed by `# The value.`
  and `VALUE = 1`, and `move-symbol` moves `VALUE`
- **THEN** `# The value.` moves with `VALUE`, and both header lines stay in `pkg/a.py`

#### Scenario: Moved code after a destination dependency
- **WHEN** the destination defines `class Base` and `def tag` after its imports, and `move-symbol` moves
  `@tag class Child(Base)` into it
- **THEN** the moved code follows `def tag`, and every destination line keeps its place

#### Scenario: Moved code takes the place of the destination's import
- **WHEN** the destination has `class Base`, then `from pkg.a import Child`, then `instance = Child()`, then
  `import os`, and `move-symbol` moves `class Child(Base)` there from `pkg/a.py`
- **THEN** the moved code replaces `from pkg.a import Child`, before `instance = Child()`

#### Scenario: Unparsable destination refused
- **WHEN** `move-symbol` moves `f` into a destination that does not parse
- **THEN** it exits 1 with the unparsable finding naming the destination, and no file changes

### Requirement: Python refactors resolve through namespace packages
A directory under one of the project's source folders that holds Python sources but no `__init__.py`, and that no
regular module or package of the same dotted name shadows, SHALL resolve as a namespace package: a module with no
bindings of its own whose submodules resolve as its attributes. A submodule found in more than one portion of a
namespace package SHALL count as unresolved. `move-module` and module renames SHALL resolve imports and attribute
chains through namespace packages like through regular packages, and `move-module` SHALL move a namespace package's
directory like a package's.

#### Scenario: Move out of a namespace package
- **WHEN** `pkg/ns/` has no `__init__.py`, `pkg/use.py` holds `from pkg.ns import m`, `import pkg.ns.m` and
  `print(m.Y, pkg.ns.m.Y)`, and `move-module` moves `pkg/ns/m.py` to `pkg/dst`
- **THEN** the lines become `from pkg.dst import m`, `import pkg.dst.m` and `print(m.Y, pkg.dst.m.Y)`

#### Scenario: Move a namespace package
- **WHEN** `move-module` moves the directory `pkg/ns` to `pkg/dst`
- **THEN** the directory moves to `pkg/dst/ns`, every import and chain naming `pkg.ns` names `pkg.dst.ns`, and the
  exit code is 0

#### Scenario: Module rename through a namespace package
- **WHEN** the module `pkg/ns/m.py` is renamed to `ns2` and a file holds `import pkg.ns.m` and uses `pkg.ns.m.Y`
- **THEN** both become `pkg.ns.ns2`

#### Scenario: Namespace package under a src layout
- **WHEN** the project keeps its code under `src/` and `src/pkg/ns/` has no `__init__.py`
- **THEN** the moves and renames above give the same result with `src/` in each path

### Requirement: Python refactors check their output before writing
Before it prints its changes or writes anything, every Python refactor SHALL check each Python file it would write. A
file that parsed before SHALL parse with its new text, else the refactor SHALL exit 1 with the unparsable finding naming
the file.
The file's new bytes SHALL decode, in the encoding they declare, to its new text, else the refactor SHALL exit 1 with
the unencodable finding naming the file and that encoding.

`move-symbol` and `move-module` SHALL then resolve the project as the move would leave it and compare it with the
project as read, each file with itself at its new path: (a) every name or attribute chain read SHALL resolve as before:
to the same declaration or module (a moved one counting as itself at its new place), to a binding the resolver cannot
follow, or to no binding; (b) a read that runs while its module is imported and followed a top-level binding of its
name SHALL still follow one; (c) a name a module binds at top level both before and after SHALL resolve as before. On
a difference the move SHALL exit 1 with the resolution-changed finding naming the file, line and name of the first one.

A refused refactor SHALL write nothing. The comparison SHALL start no language server.

#### Scenario: Rename into an encoding that cannot hold the new name
- **WHEN** `pkg/a.py` declares `# coding: ascii` and `rename` renames its `value` to `valué`
- **THEN** it exits 1 with the unencodable finding naming `pkg/a.py` and `ascii`, prints no traceback, and no file
  changes

#### Scenario: Moved code reads a builtin the destination rebinds
- **WHEN** `pkg/a.py` holds `def count(items): return len(items)` on two lines, `pkg/b.py` holds `len = 3`, and
  `move-symbol` moves `count` to `pkg/b.py`, with or without `--apply`
- **THEN** it exits 1 with the resolution-changed finding naming `pkg/b.py`, line 2 and `len`, and no file changes

#### Scenario: Output that does not parse is refused
- **WHEN** the text a move or a rename computes for a file that parsed does not parse
- **THEN** it exits 1 with the unparsable finding naming that file, and no file changes

#### Scenario: New bytes that decode to another text are refused
- **WHEN** the text a refactor computes for a file declares another encoding than the one the file is written in, and
  its bytes do not decode to that text in the declared one
- **THEN** it exits 1 with the unencodable finding naming that file and the declared encoding, and no file changes

#### Scenario: A read left without its binding is refused
- **WHEN** the texts a move computes leave a read of a name without the import that bound it
- **THEN** it exits 1 with the resolution-changed finding naming that file, the read's line and the name, and no file
  changes

#### Scenario: A use that would run before the moved declaration is refused
- **WHEN** the texts a `move-symbol` computes place the moved declaration after a top-level destination statement that
  calls it, where the destination's import of it came before that statement
- **THEN** it exits 1 with the resolution-changed finding naming the destination, that statement's line and the name,
  and no file changes

#### Scenario: A re-export that would change is refused
- **WHEN** the texts a move computes leave a package's `__init__.py` binding a name to another declaration than before,
  and no file of the project reads that name
- **THEN** it exits 1 with the resolution-changed finding naming that `__init__.py`, the binding's line and the name,
  and no file changes

#### Scenario: An export list that would change is refused
- **WHEN** the texts a `move-symbol` computes leave the moved symbol's name in the source's literal `__all__`, and no
  file of the project star-imports the source
- **THEN** it exits 1 with the resolution-changed finding naming the source, the line of its `__all__` and `__all__`,
  and no file changes

#### Scenario: Self-reference evaluated while the moved declaration is defined
- **WHEN** `pkg/a.py` has `import pkg.a` and `def f(n, step=lambda k: pkg.a.f(k), first=pkg.a.f)`, and `move-symbol`
  moves `f` to `pkg/b.py`
- **THEN** it exits 1 with the resolution-changed finding naming `pkg/b.py`, the line of the moved `def` and
  `pkg.a.f`, and no file changes

#### Scenario: Moved code reads a name the source imports and then rebinds
- **WHEN** `pkg/a.py` holds `import math as dep`, then `dep = 42`, then `def f(): return dep`, and `move-symbol` moves
  `f` to `pkg/b.py`
- **THEN** it exits 1 with the resolution-changed finding naming `pkg/a.py`, the line of `dep = 42` and `dep`, and no
  file changes

#### Scenario: An import dropped while an assignment under global still binds its name
- **WHEN** `use.py` holds `import pkg.sub as sub` and a function that declares `global sub`, reads `sub.thing.X` and
  assigns `sub = None`, and `move-module` moves `pkg/sub/thing.py` to `pkg`
- **THEN** it exits 1 with the resolution-changed finding naming `use.py`, the line of that read and `pkg.thing.X`,
  and no file changes

#### Scenario: A read that becomes bound is accepted
- **WHEN** a file reads the moved symbol at module level through an import that only a function declaring it `global`
  makes, and the move replaces that import by a top-level one
- **THEN** the move exits 0

#### Scenario: A stub that does not parse is refused
- **WHEN** a module rename runs with `--stub` and the configured stub text, filled in, does not parse
- **THEN** it exits 1 with the unparsable finding naming the stub's path, and no file changes

#### Scenario: Existing refactors unchanged
- **WHEN** any Python `dr-refactor` conformance case that existed before this requirement runs, other than the
  cases the scenarios above refuse
- **THEN** its stdout, stderr, exit code and written files are unchanged

### Requirement: Python refactors refuse a named file that does not decode
For a Python `rename`, `retarget`, `rename-map` or `move-symbol`, a file the command must read because the command
names it (`--file` with a locator, a map entry's `file` with a locator, or `--dest` of `move-symbol`) whose bytes do
not decode in the encoding it declares, UTF-8 when it declares none, SHALL be refused with
`refactor.file-undecodable` naming the file and the encoding. The exit code SHALL be 1, nothing SHALL be written,
and no traceback SHALL be printed. A file the command names without reading its text (a module rename, a
`move-module`) SHALL be handled as before.

#### Scenario: Renamed symbol's file declares an unknown encoding
- **WHEN** `rename --file pkg/a.py --symbol f --new-name g` runs and `pkg/a.py` starts with `# coding: nosuch`
- **THEN** stderr holds `refactor.file-undecodable` for `pkg/a.py` and `nosuch`, the exit code is 1, and nothing is
  written

#### Scenario: Map entry's file does not decode
- **WHEN** a `rename-map` entry names `pkg/c.py` with a symbol, and `pkg/c.py` holds a byte that is not valid UTF-8
- **THEN** stderr holds `refactor.file-undecodable` for `pkg/c.py` and `utf-8`, the exit code is 1, and nothing is
  written

#### Scenario: Move source does not decode
- **WHEN** `move-symbol --file pkg/c.py` runs and `pkg/c.py` holds a byte that is not valid UTF-8
- **THEN** stderr holds `refactor.file-undecodable` for `pkg/c.py` and `utf-8`, the exit code is 1, and nothing is
  written

#### Scenario: Move destination does not decode
- **WHEN** `move-symbol --dest pkg/c.py` runs and `pkg/c.py` holds a byte that is not valid UTF-8
- **THEN** stderr holds `refactor.file-undecodable` for `pkg/c.py` and `utf-8`, the exit code is 1, and nothing is
  written

## MODIFIED Requirements

### Requirement: Refactors edit only at references
In both languages, a file that `dr-refactor` touches SHALL change only within these permitted regions: the span of each
resolved reference to the renamed or moved module or symbol, including the name inside a forward-reference string and,
for a Python field rename, the name inside a typed dict key or `model_dump` element and a keyword argument's name; the
import item holding such a reference (its whole statement, or its whole line, when it is the statement's only item); one
inserted import statement directly after a referencing import statement or after the leading import block; and, for
`move-symbol`, the moved code's region, a relative import inside the moved code and, in a Python destination, the
imports the moved code needs: after the leading import block, inside the top-level `if TYPE_CHECKING:` block or as a new
one, and `from __future__` imports at the module's start; and `pass` in a block whose every statement the refactor
removes. Every other byte SHALL be unchanged: no import SHALL be reordered, merged, hoisted or reformatted, and no
non-import statement SHALL move. A `from` import SHALL be split only when exactly one of its names moves. CRLF line
endings and a missing final newline SHALL be preserved, and every line a refactor inserts SHALL end with the line break
the file it lands in uses.

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

#### Scenario: Moved code between files of different line endings
- **WHEN** `move-symbol` moves a function, which needs an added import, from a file with CRLF line endings into a file
  with LF line endings, and separately from an LF file into a CRLF file without a final newline
- **THEN** every line inserted into each destination ends as that destination's other lines do, the CRLF
  destination still has no final newline, and the source keeps its line endings

#### Scenario: Destination block emptied
- **WHEN** the destination's `if TYPE_CHECKING:` block holds only `from pkg.a import f`, and `move-symbol` moves `f`
  there
- **THEN** the import is removed and the block holds `pass`

### Requirement: Python moves rewrite each reference minimally
For a Python `move-module` or `move-symbol`, each occurrence of the moved module or symbol SHALL be handled by
exactly one rule, decided from the objects its names resolve to:
1. An import statement naming the old path (absolute or relative, at any scope, including `from old import *` and
   package-prefixed paths) SHALL have its path rewritten in place, keeping its alias, bound names, comments and layout.
   A relative import SHALL stay relative, recomputed from the importer's new location and the target's new location. It
   SHALL become absolute only when the target cannot be reached relatively. A relative import whose importer and target
   both move SHALL be recomputed from their new locations, so one between files that move together as one tree is
   unchanged. In a `from` import where exactly one name moves, that name SHALL be removed in place, and the moved name
   SHALL get a new `from` statement, with its alias, on the line after the statement ends, at the same indentation; in
   an inline suite (on its compound statement's header line), after `; ` at the statement's end.
2. A use whose binding still resolves after the move SHALL be unchanged. Such a binding is a name a rule-1 import
   still binds, a name another module binds explicitly (by import or assignment, at module level or inside a block of its
   module body), a name read from a module that defines a module-level `__getattr__`, or a name the function, lambda or
   comprehension scope the use is read in binds by anything other than a rule-1 import (a parameter of any kind, an
   assignment, a comprehension target), even when that scope also imports it. A name a `global` or `nonlocal`
   statement declares SHALL resolve in the scope the statement names, and a comprehension's first iterable SHALL
   resolve in the enclosing scope.
3. A use whose binding no longer resolves after the move SHALL be rewritten. Such a use reaches a submodule only as a
   package attribute, reaches the moved module by its old dotted name through a plain `import` that rule 1 rewrote to
   bind another name, or reaches the moved symbol through its old module or a star import of it. A dotted use, its
   receiver parenthesized or not, SHALL become the new dotted path, and `import <new module>` SHALL be added on the
   line after the import binding the chain's root that sits in the scope the use resolves in; when no such import sits
   there (only a function declaring `global` imports it), after the leading import block. A bare name bound by a star
   import SHALL stay as it is, and `from <new module> import <name>` SHALL be added on the line after the star import.
   No import SHALL be added where that scope already binds the same object.
An import binding SHALL be removed in place only when every use of it was rewritten by this refactor, and no `nonlocal`
statement names it. For `move-symbol`, an import statement directly in the source module's body SHALL also be removed in
place when every use of the names it binds lay in the moved code; an import inside a block of the source module SHALL
stay. In the source module, a `__all__` entry naming the moved symbol SHALL be removed from each list or tuple literal
of a top-level `__all__` assignment, annotated assignment, augmented assignment or `+` operand, and a remaining use of
the symbol (by rule 2, not a use a function, lambda or comprehension scope binds) SHALL get `from <dest> import <name>`
after the leading import block. A relative import inside the moved code SHALL be recomputed for the destination as rule
1 recomputes a moved module's own relative imports. A dotted use inside the moved code that reaches the moved symbol
through its old module SHALL become the symbol's bare name when it is evaluated only after the moved code first binds
the symbol: inside a function or lambda, or in a declaration after the first of an overload group. In the destination,
the imports the moved code needs SHALL be added:
- for each name the moved code reads that a top-level import of the source module binds, that import, made absolute;
  for each name it reads that the source module defines, `from <source module> import <name>`; each holding only the
  names the moved code reads and the destination does not already bind to the same object;
- for each name the moved code reads that a first-party star import of the source module binds,
  `from <module> import <name>`; when the moved code reads a name that no binding of the source module, star import
  it can list, or builtin explains, each star import of the source module whose names cannot be listed, made absolute
  and kept as a star import;
- after the leading import block, ordered standard library, third-party, project modules, plain
  `import` statements before `from` imports within each, then by text;
- for a name bound in the source only inside an `if TYPE_CHECKING:` block, inside the destination's top-level
  `if TYPE_CHECKING:` block, after its last statement, else in a new such block after the leading import block, with
  `from typing import TYPE_CHECKING` added when the destination does not bind it;
- for each `from __future__` import of the source that the destination lacks, as the destination's first statement
  after its docstring.

When the moved code reads a name the source module binds only inside a block other than `if TYPE_CHECKING:` (a
`try`, another `if`, a loop), `dr-refactor` SHALL exit 1 with the guarded-import finding naming the source file and
that import's line, and SHALL write nothing. The leading import block is the first contiguous run of import
statements, ending at the first non-import statement; in a file without imports it is the position after the module
docstring and `__future__` imports. Edits SHALL be located by source character, so non-ASCII text before them on the
line does not shift them. When an added import or the moved code would bind a name that already resolves to a
different object in that scope, `dr-refactor` SHALL exit 1 with the name-conflict finding naming the file and line,
and SHALL write nothing.

#### Scenario: Multi-name from-import split in place
- **WHEN** `move-module` moves `pkg/sql/client.py` to `pkg/database` and a file has
  `from pkg.sql import dialects, client` between `import sys` and `import os`
- **THEN** that line becomes `from pkg.sql import dialects`, the next line is `from pkg.database import client`, and
  every other line is byte-identical

#### Scenario: Split inside an inline suite
- **WHEN** a file has `if TYPE_CHECKING: from pkg.a import f, g`, and `move-symbol` moves `f` to `pkg/b.py`
- **THEN** the line becomes `if TYPE_CHECKING: from pkg.a import g; from pkg.b import f`

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

#### Scenario: Module outside any package moved into a package
- **WHEN** `a.py`, which no package holds, moves into `dest/`, and `use.py` holds `import a` and `a.func()`
- **THEN** the import becomes `import dest.a`, the use becomes `dest.a.func()`, and no import is added

#### Scenario: Symbol reached through a module alias
- **WHEN** `move-symbol` moves `f` from `pkg/a.py` to `pkg/b.py` and a file has `import pkg.a as pa` used only as
  `pa.f()`
- **THEN** the use becomes `pkg.b.f()`, `import pkg.b` replaces `import pkg.a as pa` in place, and every other line
  is unchanged

#### Scenario: Parenthesized receiver
- **WHEN** `move-symbol` moves `f` from `pkg/a.py` to `pkg/b.py`, and a file with `import pkg.a as pa` reads
  `(pa).f()` and has `def g(x=( pa ).f)`
- **THEN** both reads become `pkg.b.f`, and `import pkg.b` replaces `import pkg.a as pa` in place

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

#### Scenario: Relative import of the moved package through its parent
- **WHEN** `move-module` moves `pkg/sub` to the project root, and `pkg/sub/use.py` has `from ..sub import helper`
- **THEN** it becomes `from . import helper`

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

#### Scenario: Destination import order
- **WHEN** the moved `f` reads `annotations`-dependent annotations, `json`, `yaml`, `pkg.c.C` through
  `from .c import C`, and `g` that `pkg/a.py` defines, and the source imports them as `from .c import C`,
  `import yaml`, `import json` and `from __future__ import annotations`
- **THEN** the destination gains `from __future__ import annotations` as its first statement, and after its leading
  import block `import json`, `import yaml`, `from pkg.a import g` and `from pkg.c import C`, in that order

#### Scenario: Import used only by the moved code inside a block stays
- **WHEN** `pkg/a.py` holds `if TYPE_CHECKING:` with `from .x import T`, and a `try:` with `import json` and
  `except ImportError: json = None`, and only the moved `f` reads `T`
- **THEN** both blocks of `pkg/a.py` are unchanged

#### Scenario: TYPE_CHECKING import follows the moved code
- **WHEN** the moved `f` reads `T`, bound in `pkg/a.py` only by `from .x import T` under `if TYPE_CHECKING:`, and the
  destination has no `TYPE_CHECKING` block
- **THEN** the destination gains `from typing import TYPE_CHECKING` after its leading import block, then
  `if TYPE_CHECKING:` holding `from pkg.x import T`; with an existing top-level `if TYPE_CHECKING:` block, the import
  is added as its last statement instead

#### Scenario: Other guarded import refused
- **WHEN** the moved `f` reads `json`, bound in `pkg/a.py` only inside `try: import json` / `except ImportError:
  json = None`
- **THEN** stderr ends with the guarded-import finding naming `pkg/a.py` and the line of `import json`, the exit code
  is 1 and no file changes

#### Scenario: Relative import inside the moved code
- **WHEN** `move-symbol` moves `f` from `pkg/a/m.py` to `pkg/b/d.py` and `f`'s body holds `from .x import y`
- **THEN** in `pkg/b/d.py` it becomes `from ..a.x import y`, and an absolute import in `f`'s body is unchanged

#### Scenario: Qualified self-reference inside the moved code
- **WHEN** `move-symbol` moves `f` from `pkg/a.py` to `pkg/b.py`, `f`'s body holds `pkg.a.f(n - 1)`, and nothing else in `f` reads `pkg`
- **THEN** in `pkg/b.py` it becomes `f(n - 1)` and `import pkg.a` is not added

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

#### Scenario: Import re-bound from another scope
- **WHEN** `move-symbol` moves `f` out of `pkg/a.py`; `outer()` has `import pkg.a as pa` and reads `pa.f()`, and its
  inner function declares `nonlocal pa` and imports `pkg.a as pa`; and another file reads `pa.f()` at module level,
  where only a function declaring `global pa` imports `pkg.a as pa`
- **THEN** both reads become `pkg.b.f()`, `import pkg.b` is added on the line after `outer`'s import and after the
  other file's leading import block, and no import is added inside the inner functions

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
