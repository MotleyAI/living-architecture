# refactor Specification

## Purpose
Verified refactoring for both languages: `dr-refactor` rewrites a rename or move across a project,
`dr-compliance` reports what would make that rewrite unverifiable, and `dr-mock-lint` keeps test doubles
type-bound, so the type-check ratchet plus the tests prove nothing was missed.

## Requirements

### Requirement: dr-* inputs are routed by file language
`dr-refactor`, `dr-compliance` and `dr-mock-lint` SHALL route each input file to the twin of its language,
decided by the registry's source extensions. `dr-refactor`'s language SHALL be the language of `--file`
(`rename`, `move-symbol`) or `--module` (`move-module`); a source of an unregistered extension, a `--dest`
of another language, or a `--module` directory whose expansion holds more than one language, SHALL exit 1 with a
finding. For `dr-compliance` and `dr-mock-lint`, an explicit file of
an unregistered extension, or matching the language's `declaration_globs`, SHALL be skipped with a warning on
stderr; a directory SHALL expand only to files of the repo's languages, or of every registered language when the repo has none, excluding `declaration_globs` and
`excluded_dirs`. The other language's files SHALL run in its twin with the same working directory. Output
SHALL be one block per language in registry id order, each exactly as that language's twin prints it alone;
stderr SHALL be relayed; the exit code SHALL be the maximum. When the other twin cannot run or fails with exit
2 or a signal, the command SHALL print nothing on stdout, report the failure as the forwarding rules
define, and exit 2.

#### Scenario: Python-only repo directory expansion is unchanged
- **WHEN** `dr-compliance src` runs in a repo whose only repo language is Python and `src` also holds `app.js`
- **THEN** only the `.py` files are checked and stdout equals today's golden

#### Scenario: Mixed explicit files
- **WHEN** `dr-mock-lint tests/test_a.py web/a.test.ts` runs through either twin, both files violating
- **THEN** stdout is the Python block followed by the TypeScript block, identical for both invoking twins, and the exit code is 1

#### Scenario: Declaration file skipped
- **WHEN** `dr-compliance types/api.d.ts` runs
- **THEN** a warning names the skipped file on stderr and the exit code is 0

#### Scenario: Relative paths from a subdirectory
- **WHEN** `dr-refactor --project .. rename --file src/a.ts --name foo --new-name bar` runs through the PyPI twin from a subdirectory
- **THEN** the forwarded run resolves every path against the same working directory and the output equals the npm twin's own run

#### Scenario: Cross-language destination
- **WHEN** `dr-refactor move-symbol --file pkg/a.py --name foo --dest web/b.ts` runs
- **THEN** it exits 1 with the cross-language finding and changes nothing

#### Scenario: Mixed-language directory refused
- **WHEN** `dr-refactor move-module --module pkg --dest lib` runs and `pkg` holds both `.py` and `.ts` sources
- **THEN** it exits 1 with a mixed-language finding and changes nothing

### Requirement: Refactor output format
`dr-refactor` SHALL print a header naming the refactor, then one unified diff per changed file sorted by
path (`--- a/<path>`, `+++ b/<path>`, three context lines, no end-of-file marker), a `rename from` / `rename
to` pair for every moved file, then the dry-run or applied footer. Every header, footer and error SHALL come
from the findings registry; no checker or library message text SHALL be printed. The diff format SHALL be
pinned by shared vectors that both twins pass, covering a missing final newline, CRLF line endings, created
and deleted files, and paths with spaces or non-ASCII characters.

#### Scenario: TS rename dry-run
- **WHEN** `dr-refactor rename --file src/a.ts --name foo --new-name bar` runs on a project where `src/b.ts` imports `foo`
- **THEN** stdout is the rename header, the diffs of `src/a.ts` and `src/b.ts` in path order, and the dry-run footer naming 2 files, and no file changes

#### Scenario: Diff vectors
- **WHEN** either twin's suite runs
- **THEN** its diff formatter reproduces every shared diff vector byte for byte

### Requirement: TypeScript refactors are computed per project
The TypeScript `dr-refactor` SHALL load the tsconfig named by `index.yaml`'s `typescript.tsconfig` when set;
otherwise, as TypeScript's own tooling does, it SHALL look at the `tsconfig.json` files from the source file's
directory up to `<project>` and take the outermost one whose reference graph contains the file (a solution
config), else the nearest one. It SHALL load every project in that reference graph, each with its own compiler
options. `dr-compliance` and `dr-mock-lint` SHALL pick each input file's tsconfig the same way.
An `architecture/index.yaml` that exists but is not valid UTF-8 or not valid YAML SHALL be an error, never a reason
to fall back: a duplicate key SHALL be reported with the `c4.index-duplicate-key` wording, any other problem with
the `c4.index-invalid-yaml` wording, and the command SHALL exit as for a named tsconfig that does not exist. Only a
missing `index.yaml`, or one that names no tsconfig, SHALL fall back.
A source file SHALL belong to the first project in depth-first preorder that contains it; a file in no project
SHALL exit 1. A rename SHALL be computed in every project that contains or references the owning project;
identical edits SHALL be merged, and differing edits to one span SHALL exit 1. The whole change set SHALL be
computed and validated before any write: overlapping edits, a move onto an existing path, or a missing
destination SHALL exit 1 with nothing written. A dry-run SHALL never write. The TypeScript used SHALL be the
twin's bundled one; target-repo code SHALL never be loaded.

#### Scenario: Rename across project references
- **WHEN** a solution tsconfig references `core` and `app`, `app` imports `foo` from `core`, and `foo` is renamed in `core`
- **THEN** the edits in both projects are printed

#### Scenario: tsconfig below the project root
- **WHEN** `index.yaml` names no tsconfig, `<project>` has no `tsconfig.json`, and `web/tsconfig.json`
  includes `web/src`
- **THEN** `dr-refactor` and `dr-compliance` on `web/src/a.ts` use `web/tsconfig.json`'s project and options

#### Scenario: Duplicate key in the index
- **WHEN** `architecture/index.yaml` repeats a key and `dr-refactor`, `dr-compliance` or `dr-mock-lint` runs on a TS
  file
- **THEN** it prints `index.yaml is not valid YAML: ` followed by the duplicate-key message, exits as for a missing
  named tsconfig (1 for `dr-refactor`, 2 for `dr-compliance` and `dr-mock-lint`) and writes nothing

#### Scenario: Invalid index YAML
- **WHEN** `architecture/index.yaml` is not valid YAML or not valid UTF-8 and `dr-refactor` runs on a TS file
- **THEN** it prints `index.yaml is not valid YAML`, exits 1 and writes nothing

#### Scenario: Projects with different compiler options
- **WHEN** `app` uses a `paths` alias that `core` does not declare
- **THEN** the alias import in `app` is rewritten by the rename

#### Scenario: File outside every project
- **WHEN** `--file` names a TS file no project includes
- **THEN** it exits 1 with the outside-project finding

#### Scenario: Move onto an existing file
- **WHEN** `--apply move-module --module src/a.ts --dest lib` runs and `lib/a.ts` exists
- **THEN** it exits 1 with the collision finding and no file changes

### Requirement: TypeScript locators
`--line` and `--col` SHALL be 1-based and `--offset` 0-based; columns and offsets SHALL count Unicode code
points, and a column SHALL count within its line excluding the line terminator. A line, column or offset out
of range SHALL exit 1 with a finding. `--name` SHALL select the first declaration named NAME in document order
(function, class, interface, type alias, enum, variable, method or property), else the first identifier NAME;
none SHALL exit 1 with the symbol-not-found finding. No locator SHALL exit 1 with the no-locator finding.

#### Scenario: Astral character before the symbol
- **WHEN** a line is `const s = "😀"; const foo = 1;` and `--line 1 --col 22` points at `foo`
- **THEN** `foo` is renamed

#### Scenario: Column out of range
- **WHEN** `--col` exceeds the line's length plus one
- **THEN** it exits 1 with the out-of-range finding

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

### Requirement: TypeScript move-symbol and move-module
`move-symbol` SHALL apply the language service's move-to-file refactor for a top-level declaration into the
existing `--dest` file, rewriting every import of it. Every re-export of the moved symbol, named, default or
through `export *`, SHALL resolve to the new file. A location with no applicable move SHALL exit 1 with a
not-movable finding. `move-module` SHALL move a file or directory into the existing `--dest` directory and
rewrite every import of it.

#### Scenario: Move a function with importers
- **WHEN** `--apply move-symbol --file src/a.ts --name foo --dest src/b.ts` runs and `src/c.ts` imports `foo` from `./a`
- **THEN** `foo` is in `src/b.ts`, `src/c.ts` imports it from `./b`, and the applied footer lists the changed files

#### Scenario: Default export and re-export
- **WHEN** the moved symbol is a default export re-exported by `src/index.ts`
- **THEN** every importer and the re-export resolve to the new file

#### Scenario: Barrel re-export
- **WHEN** `src/index.ts` has `export * from './a'` and `foo` moves from `src/a.ts` to `src/b.ts`
- **THEN** `src/index.ts` re-exports `foo` from `./b`

#### Scenario: Not movable
- **WHEN** the location is inside a function body
- **THEN** it exits 1 with the not-movable finding

#### Scenario: Move a directory
- **WHEN** `--apply move-module --module src/util --dest src/lib` runs
- **THEN** `src/util` becomes `src/lib/util` and every import of it is rewritten

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
report `x.NAME` and `x['NAME']` (a plain string literal) accesses whose receiver's type is `any`, and each TypeScript string-member form of the language
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

### Requirement: TypeScript mock lint
TypeScript `dr-mock-lint` SHALL flag: `fn()` on `vi` or `jest` with neither a type argument nor an
implementation; `mock`, `doMock` or `unstable_mockModule` on `vi` or `jest` with a factory whose module is not
given in the typed form (Vitest: an `import('…')` first argument; Jest: a `typeof import('…')` type argument),
or whose `import('…')` does not resolve; and, in files matching the test globs, a double assertion `as unknown
as T` or `as any as T`. A call without a factory, or with only an options object, SHALL pass. `vi` and `jest`
SHALL be recognized only when bound to an import from `vitest` or `@jest/globals` (aliases included) or to the
unshadowed global. There SHALL be no waiver.

#### Scenario: Bare fn
- **WHEN** a test has `const f = vi.fn()`
- **THEN** it is reported; `vi.fn<typeof g>()` and `vi.fn(() => 1)` are not

#### Scenario: Untyped module factory
- **WHEN** a test has `vi.mock('./api', () => ({ get: vi.fn<typeof get>() }))`
- **THEN** it is reported; `vi.mock(import('./api'), …)` and `vi.mock('./api')` are not

#### Scenario: Shadowed receiver
- **WHEN** a file declares its own local `vi` and calls `vi.fn()`
- **THEN** nothing is reported

#### Scenario: Double assertion in a test
- **WHEN** `a.test.ts` has `const db = {} as unknown as Db` and `src/a.ts` has the same line
- **THEN** only the test file's line is reported

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
- Python 3.14 t-strings.

Source positions SHALL be compared in characters, so non-ASCII text anywhere in a module SHALL NOT break a
refactor.

#### Scenario: Annotated parameter with a keyword default inside the annotation
- **WHEN** `dr-refactor rename` runs on a project whose module holds `async def probe(p: Annotated[_Payload | None, Field(description="param text")] = None) -> str:`
- **THEN** it prints the rename's diff and exits 0

#### Scenario: f-string concatenated with a literal holding a parenthesis
- **WHEN** a module of the project holds `c = g(f"{d}" "(")`, or a call whose argument is `"…'QueryFinish' "` followed by `f"AND user = '{u.name}' "` and `"AND query LIKE '%getSetting(%readonly%'"`
- **THEN** a rename in that project prints its diff and exits 0

#### Scenario: Class keywords and try-else-finally
- **WHEN** a module holds `class A(B, metaclass=M, x=")"):` and a `try` with `except`, `else` and `finally` blocks whose bodies hold strings with parentheses
- **THEN** a rename of a name used in both prints every occurrence and exits 0

#### Scenario: t-string on Python 3.14
- **WHEN** the twin runs on Python 3.14 and a module holds `f(t"{a}(", ")")`
- **THEN** a rename of `a` prints its diff and exits 0

#### Scenario: Non-ASCII text before an annotation
- **WHEN** a module holds `def f(s: str = "😀", p: A[F(d="(")] = None) -> str: ...`
- **THEN** a rename of `p` prints its diff and exits 0

### Requirement: A Python walker gap is refused with a located finding
When rope's walker fails on a module while the Python `dr-refactor` computes a refactor, or leaves part of it
uncovered, `dr-refactor` SHALL stop. It SHALL print the `refactor.rope-walk` finding on stderr, naming the file
and the line of the construct, and exit 1. It SHALL write no file, with or without `--apply`, and print no rope
or library message text. The line SHALL be:
- the start line of the first uncovered syntax node or string literal in source order;
- else the start line of the first top-level statement the walker cannot cover on its own;
- else 1.

A gap that does not crash SHALL be refused like one that does. Any other failure SHALL NOT be reported as a
walker gap.

#### Scenario: Gap reported at the construct, not at the drift
- **WHEN** the walker leaves a parameter annotation on line 3 uncovered and its token search fails on line 9
- **THEN** stderr is `refactor.rope-walk` naming the module and line 3, the exit code is 1 and no file changes

#### Scenario: Apply writes nothing on a gap
- **WHEN** `dr-refactor --apply rename …` hits a walker gap in any module it analyses
- **THEN** it exits 1 with `refactor.rope-walk` and every file of the project is unchanged

#### Scenario: Silent gap refused
- **WHEN** the walker finishes a module without error but leaves a string literal's tail uncovered
- **THEN** `dr-refactor` exits 1 with `refactor.rope-walk` naming that literal's line

### Requirement: A Python dry-run writes nothing
The Python `dr-refactor` without `--apply` SHALL leave the project tree unchanged. In particular it SHALL NOT
create rope's `.ropeproject` folder. With `--apply`, it SHALL change only the files the refactor rewrites,
creates, moves or deletes.

#### Scenario: No rope folder after a dry-run
- **WHEN** `dr-refactor rename --file pkg/a.py --name foo --new-name bar` runs on a project without `.ropeproject`
- **THEN** the project still has no `.ropeproject` and no file changes

#### Scenario: No rope folder after an apply
- **WHEN** the same rename runs with `--apply`
- **THEN** only the renamed files change and no `.ropeproject` is created

### Requirement: Python rope-walk compliance check
The Python `dr-compliance` check `rope-walk` SHALL walk each file as `dr-refactor` would. For every file the
walker cannot cover, it SHALL report one `compliance.rope-walk` finding at the line `dr-refactor` would name. A
file that does not parse SHALL get only its `parse-error` finding.

#### Scenario: Every formerly failing construct passes
- **WHEN** `dr-compliance --select rope-walk` runs on files holding every construct of "Python refactors walk every source construct"
- **THEN** nothing is printed and the exit code is 0

#### Scenario: Uncoverable file listed
- **WHEN** the walker cannot cover `pkg/a.py` at line 3, and `pkg/b.py` is clean
- **THEN** stdout is the single `compliance.rope-walk` line for `pkg/a.py` and line 3, and the exit code is 1

#### Scenario: Parse error takes precedence
- **WHEN** `dr-compliance` runs on a `.py` file with a syntax error
- **THEN** only its `parse-error` finding is printed

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
the write, `dr-refactor` SHALL print the `refactor.file-changed` finding naming that file on stderr, write nothing and
exit 1. A module rename SHALL keep rope's behaviour alone.

basedpyright SHALL be the version the PyPI twin ships, started from la's own environment, run with la's
pyright#11919 patch, reading the project's own configuration and finding the project's interpreter as basedpyright
does. It SHALL run with its working directory outside the project, without the user site, without bytecode
writing and with neither the working directory nor an inherited `PYTHONPATH` on the interpreter's path, so
no target-repo code runs. A language server
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
- for a `TypedDict` K, an argument to a parameter annotated K (a positional argument only before any `*` unpacking,
  and to an instance method only through a receiver proven to be its class or an instance of it), a value assigned
  to a variable annotated K, and a value returned from a function annotated to return K;
- a dict literal nested at the value of a rewritten-target key or keyword whose field type, after removing `None`
  from a union and unwrapping `list`, `Sequence`, `set`, `frozenset`, `tuple` and the values of `dict[str, ...]`, is
  a keyed class;
- a name bound exactly once in its function scope, by `name = {...}`, declared neither `global` nor `nonlocal`, not
  captured by an inner scope, whose every use is one of the arguments above.

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

### Requirement: Python parameter renames cover every parameter kind
The Python `dr-refactor rename` SHALL rename a `def` or `async def` parameter of any kind (positional-only,
positional-or-keyword, keyword-only, `*args`, `**kwargs`) located by `--line`/`--col`, `--offset` or `--name`, at its
declaration, at a use in its function or at a `name=` keyword of a call. It SHALL rewrite each renamed declaration,
every use of it in its function including nested scopes, and every `name=` keyword at a call the checker resolves to
a renamed declaration. A `name=` keyword SHALL resolve only to a positional-or-keyword or keyword-only parameter, never
to a positional-only parameter, `*args` or `**kwargs`. Positional arguments, keywords that reach the function
unresolved (`**mapping` unpacking, `**kwargs` forwarding) and every other text SHALL be unchanged.

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
- **THEN** the `**mapping` and `wrap` sites are unchanged, and the `functools.partial` keyword, which the checker
  resolves to `kwonly`, is renamed

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

### Requirement: Member renames refuse on untyped receivers
A member rename SHALL be a `dr-refactor rename` whose symbol is declared in a class body: in Python a method (sync
or async), property, class attribute, instance attribute (`self.x`) or field; in TypeScript a property, method or
accessor of a class, interface or type literal. A blind spot of the old name OLD SHALL be, in a source file of the
rename's language under the project:
- an attribute access `x.OLD` (in TypeScript also `x['OLD']`, the element a plain string literal) whose receiver
  the checker types as unknown (Python `Unknown`, `Any` or a union holding either; TypeScript `any`);
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

#### Scenario: TypeScript element access on an any receiver
- **WHEN** property `Store.getModel` is renamed and a file holds `function g(o: any) { return o['getModel']('a') }`
- **THEN** the rename refuses with that site's `attr-blindspot` line, and `dr-compliance --select attr-blindspot
  --attr getModel` reports the same line

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
A target segment OLD that resolves to a declaration the rename leaves unchanged SHALL be unchanged and unlisted,
with or without `--docs`.

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

#### Scenario: Target form with an unresolved callee
- **WHEN** a test holds `def test_t(mocker): mocker.patch("pkg.engine.SearchQueryEngine.save_model")` with
  `mocker` unannotated
- **THEN** the member rename refuses with that target's `refactor.unresolved-target` line

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
  segment), optionally preceded by dotted segments that SHALL form a suffix of the declaring module's dotted path
  (Python: the module's name from its source folder; TypeScript: the file's project-relative path without its
  source extension, `/` read as `.`).
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
