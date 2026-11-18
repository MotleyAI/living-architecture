# refactor Specification

## Purpose
Verified refactoring for both languages: `dr-refactor` rewrites a rename or move across a project,
`dr-compliance` reports what would make that rewrite unverifiable, and `dr-mock-lint` keeps test doubles
type-bound, so the type-check ratchet plus the tests prove nothing was missed.

## Requirements

### Requirement: dr-* inputs are routed by file language
`dr-refactor`, `dr-compliance` and `dr-mock-lint` SHALL route each input file to the twin of its language,
decided by the registry's source extensions. `dr-refactor`'s language SHALL be the language of `--file`
(`rename`, `retarget`, `move-symbol`), of every entry's `file` or `module` (`rename-map`) or of `--module` (`move-module`); a
source of an unregistered extension, a `--dest` of another language, or a `--module` directory whose expansion
holds more than one language, SHALL exit 1 with a finding. For `dr-compliance` and `dr-mock-lint`, an explicit file
of an unregistered extension, or matching the language's `declaration_globs`, SHALL be skipped with a warning on
stderr; a directory SHALL expand only to files of the repo's languages, or of every registered language when the
repo has none, excluding `declaration_globs` and `excluded_dirs`. The other language's files SHALL run in its twin
with the same working directory and the same options. Output SHALL be one block per language in registry id order,
each exactly as that language's twin prints it alone; stderr SHALL be relayed; the exit code SHALL be the maximum.
When the other twin cannot run or fails with exit 2 or a signal, the command SHALL print nothing on stdout, report
the failure as the forwarding rules define, and exit 2.

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
- **WHEN** `dr-refactor --project .. rename --file src/a.ts --symbol foo --new-name bar` runs through the PyPI twin from a subdirectory
- **THEN** the forwarded run resolves every path against the same working directory and the output equals the npm twin's own run

#### Scenario: Cross-language destination
- **WHEN** `dr-refactor move-symbol --file pkg/a.py --symbol foo --dest web/b.ts` runs
- **THEN** it exits 1 with the cross-language finding and changes nothing

#### Scenario: Mixed-language directory refused
- **WHEN** `dr-refactor move-module --module pkg --dest lib` runs and `pkg` holds both `.py` and `.ts` sources
- **THEN** it exits 1 with a mixed-language finding and changes nothing

#### Scenario: TypeScript map through the PyPI twin
- **WHEN** `dr-refactor rename-map map.yaml` runs through the PyPI twin and every entry names a `.ts` file
- **THEN** the output and exit code equal the npm twin's own run

#### Scenario: A module entry routes by its path
- **WHEN** a map holds a symbol entry on `pkg/a.py` and a module entry `{module: web/b.ts, new_name: c}`
- **THEN** stderr is `refactor.map-mixed-languages`, through either invoking twin, and the exit code is 2

#### Scenario: Base comparison in both blocks
- **WHEN** `dr-mock-lint --base main tests/test_a.py web/a.test.ts` runs through either twin
- **THEN** each language's block holds only its new findings, identical for both invoking twins

### Requirement: Refactor output format
`dr-refactor` SHALL print one header line per refactor entry in order (a rename map's entries in map order, entries
merged as duplicates counting once), then one unified diff per changed file sorted by path (`--- a/<path>`,
`+++ b/<path>`, three context lines, no end-of-file marker), the type-check baseline included, a `rename from` /
`rename to` pair for every moved file, then the dry-run or applied footer. Progress, refusals, leftovers and warnings
SHALL be printed on stderr. Every header, footer, progress line, warning and error SHALL come from the findings
registry; no checker or library message text SHALL be printed, except a failed checker's cause after its finding. The
diff format SHALL be pinned by shared vectors that both twins pass, covering a missing final newline, CRLF line
endings, created and deleted files, and paths with spaces or non-ASCII characters.

#### Scenario: TS rename dry-run
- **WHEN** `dr-refactor rename --file src/a.ts --symbol foo --new-name bar` runs on a project where `src/b.ts` imports `foo`
- **THEN** stdout is the rename header, the diffs of `src/a.ts` and `src/b.ts` in path order, and the dry-run footer naming 2 files, and no file changes

#### Scenario: Map headers
- **WHEN** a map holds a rename entry and then a retarget entry
- **THEN** stdout starts with the rename header line and then the retarget header line

#### Scenario: Merged entries share a header
- **WHEN** entries 1 and 2 locate the same symbol with the same new name
- **THEN** stdout holds one header line for them

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

### Requirement: Locators
In both twins, `--line` and `--col` SHALL be 1-based and `--offset` 0-based; columns and offsets SHALL count Unicode
code points of the file as read, every line terminator (`\r\n`, `\n`, a lone `\r`) included in an offset, and a column
SHALL count within its line excluding the line terminator. A line, column or offset out of range SHALL exit 1 with a
finding, whose count is the file's code points for an offset. `--symbol` SHALL locate as the symbol-path requirement
defines. No locator SHALL exit 1 with the no-locator finding, except in a `rename`, which then renames the module
`--file` names.

#### Scenario: Astral character before the symbol
- **WHEN** a line is `const s = "😀"; const foo = 1;` and `--line 1 --col 22` points at `foo`
- **THEN** `foo` is renamed

#### Scenario: Column out of range
- **WHEN** `--col` exceeds the line's length plus one
- **THEN** it exits 1 with the out-of-range finding

#### Scenario: Module rename without a locator
- **WHEN** `rename --file pkg/sql/client.py --new-name cli2` runs with no locator
- **THEN** its output equals that of the rename located on an import of `pkg.sql.client`

#### Scenario: TypeScript module rename without a locator
- **WHEN** `rename --file src/a.ts --new-name b` runs with no locator
- **THEN** `src/a.ts` is renamed as a TypeScript module rename, not refused with the no-locator finding

#### Scenario: Retarget without a locator
- **WHEN** `retarget --file src/a.ts --target bar` runs with no locator
- **THEN** it exits 1 with the no-locator finding

#### Scenario: Module located on a dotted import
- **WHEN** a `rename` is located on `mod` in `import pkg.mod` or in `from pkg.mod import X`
- **THEN** `pkg/mod.py` is renamed as a module rename, and no name declared in it is renamed

#### Scenario: Offset after CRLF line breaks
- **WHEN** a file with CRLF line endings declares `foo` on its third line and `--offset` counts both characters of each
  earlier line break to reach it
- **THEN** both twins rename `foo`, and an offset one past the file's code points exits 1 with the out-of-range finding
  naming that count

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
rewrite every import of it, and every mock module path as "TypeScript module moves rewrite mock module paths" defines.

#### Scenario: Move a function with importers
- **WHEN** `--apply move-symbol --file src/a.ts --symbol foo --dest src/b.ts` runs and `src/c.ts` imports `foo` from `./a`
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

#### Scenario: Move a mocked module
- **WHEN** `--apply move-module --module src/api.ts --dest src/lib` runs and a test holds `vi.mock('../src/api')`
- **THEN** the test reads `vi.mock('../src/lib/api')`

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
The Python `dr-refactor` SHALL compute every move over modules that rope's source walker fully covers among the
modules rope walks: those of the move. Every syntax node SHALL be walked, except expression contexts, operators,
`with` items and the internals of f-strings and t-strings. Every string literal SHALL be covered over its full source
text, including every piece of an implicit concatenation and any `r`/`b`/`u`/`f`/`t` prefix in any order and case;
covering surrounding parentheses as well is allowed. This SHALL hold for every construct of the Python versions the
package supports. The following SHALL be refactored like any other code:
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

#### Scenario: A module rope does not walk
- **WHEN** a rename's old name occurs only in modules other than the entry's, each holding a construct rope's walker
  cannot cover, and the checker resolves every occurrence
- **THEN** the rename prints its diff and exits 0 without `refactor.rope-walk`

#### Scenario: A rename walks no module
- **WHEN** a rename's entry module and every module holding its old name hold a construct rope's walker cannot cover
- **THEN** the rename prints its diff and exits 0 without `refactor.rope-walk`

### Requirement: A Python walker gap is refused with a located finding
When rope's walker fails on a module while the Python `dr-refactor` computes a move, or leaves part of it uncovered,
`dr-refactor` SHALL refuse with the `refactor.rope-walk` finding on stderr, naming the file and the line of the
construct, and exit 1. Every gap in a module rope walks before the reference search SHALL be found in the `checks`
phase, before any reference search, and all of them reported together; a gap met later SHALL refuse the entry that
met it while the run goes on. It SHALL write no file, with or without
`--apply`, and print no rope or library message text. The line SHALL be:
- the start line of the first uncovered syntax node or string literal in source order;
- else the start line of the first top-level statement the walker cannot cover on its own;
- else 1.

A gap that does not crash SHALL be refused like one that does. Any other failure SHALL NOT be reported as a
walker gap.

#### Scenario: Gap reported at the construct, not at the drift
- **WHEN** the walker leaves a parameter annotation on line 3 uncovered and its token search fails on line 9
- **THEN** stderr ends with `refactor.rope-walk` naming the module and line 3, the exit code is 1 and no file changes

#### Scenario: Apply writes nothing on a gap
- **WHEN** `dr-refactor --apply move-symbol …` hits a walker gap in any module it analyses
- **THEN** it exits 1 with `refactor.rope-walk` and every file of the project is unchanged

#### Scenario: Silent gap refused
- **WHEN** the walker finishes a module without error but leaves a string literal's tail uncovered
- **THEN** `dr-refactor` exits 1 with `refactor.rope-walk` naming that literal's line

### Requirement: A Python dry-run writes nothing
The Python `dr-refactor` without `--apply` SHALL leave the project tree unchanged. In particular it SHALL NOT
create rope's `.ropeproject` folder. With `--apply`, it SHALL change only the files the refactor rewrites,
creates, moves or deletes, and the type-check baseline it realigns.

#### Scenario: No rope folder after a dry-run
- **WHEN** `dr-refactor rename --file pkg/a.py --symbol foo --new-name bar` runs on a project without `.ropeproject`
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
   import, a name another module binds explicitly (by import or assignment), or a name the function, lambda or
   comprehension scope the use is read in binds by anything other than a rule-1 import (a parameter of any kind, an
   assignment, a comprehension target), even when that scope also imports it. A name a `global` or `nonlocal`
   statement declares SHALL resolve in the scope the statement names, and a comprehension's first iterable SHALL
   resolve in the enclosing scope.
3. A use whose binding no longer resolves after the move SHALL be rewritten. Such a use reaches a submodule only as a
   package attribute, or reaches the moved symbol through its old module or a star import of it. A dotted use, its
   receiver parenthesized or not, SHALL become the new dotted path, and `import <new module>` SHALL be added on the
   line after the import binding the chain's root that sits in the scope the use resolves in; when no such import sits
   there (only a function declaring `global` imports it), after the leading import block. A bare name bound by a star import SHALL stay as it is, and `from <new module> import <name>` SHALL be
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

### Requirement: Python renames include every reference basedpyright resolves
For a Python `rename` of a symbol other than a module, `dr-refactor` SHALL edit every occurrence the run's occurrence
index resolves to a declaration the rename renames: every declaration of the renamed hierarchy by default, only the
located one with `--no-in-hierarchy`; and every name, import or alias occurrence the checker resolves to no declaration
that Python's scoping and import rules over the project's source folders resolve to one of them. These references SHALL
include forward-reference strings (`"X"`,
`Optional["X"]`, `list["X"]`, `"X | None"`), keyword arguments of dataclass and Pydantic fields at calls whose callee
is the owning class, a subclass or a `type[...]` of either, receivers typed by a parameter annotation, an attribute
annotation (`self.x: T` or a class-body `x: T`), a return annotation or inference, `isinstance`-narrowed receivers,
and `super().name(...)` calls. Every edit SHALL replace exactly the old name, located by source character in
the file's text as read; positions SHALL be correct after non-ASCII and astral characters and with CRLF line endings.
Edits SHALL NOT overlap unless identical; identical edits SHALL be merged. When a file changes between its read and
the write, `dr-refactor` SHALL print the `refactor.file-changed` finding naming that file on stderr, write nothing and
exit 1.

A Python module rename SHALL move the module's file, or a package's directory, to the new name and rewrite, in every
project Python source, each spelling of the module in an import: the renamed segment of a dotted `import` (with or
without `as`), the module path of a `from … import` (absolute or relative) and an imported name that is the module
(`from pkg import old`, `from . import old`, with or without `as`); and every name or attribute load that Python's
scoping and import rules resolve to the module through those bindings (`old.X`, `pkg.old.X`, `other.old.X` where
module `other` binds it); and each string of a module's literal `__all__` that the module resolves to the renamed
module (a binding of it, or the package's own submodule). An `as` alias spelled exactly like the module's own name
SHALL be renamed with every use it binds; any other alias and its uses SHALL be left. Every edit SHALL keep each line's
ending and the file's encoding.
With `--stub REMOVAL`, every module file a run's module renames move SHALL get, after the moves, a stub at its old path
holding `refactor.python.moved_module_stub` with `{old}` and `{new}` (its own old and new dotted names) and
`{removal}` replaced, shown as a new file in the diff; a module whose move a keep drops SHALL get none. `--stub` SHALL
be refused in the `checks` phase, with exit 2 and nothing written: with `refactor.stub-unconfigured` when no stub is
configured, and with `refactor.stub-not-module` when the run renames no module, or one of its module renames is not of
a module file (a package, a namespace package or a library module's alias).
A module rename SHALL be refused with the `refactor.name-conflict` finding when its package already binds the new name
in the code before the refactor (a module of that name, naming it at line 1; a package of that name, naming its
`__init__.py`, else its first Python file by path, at line 1; or a binding in the package's `__init__.py`, naming its
line), in the `checks` phase before any reference search, or when its edits would change a binding as the requirement
that renames keep every reference's binding defines, in the `conflicts` phase; either way writing nothing and exiting 1.

basedpyright SHALL be the version the PyPI twin ships, started from la's own environment, run with la's
pyright#11919 patch, reading the project's own configuration and finding the project's interpreter as basedpyright
does. It SHALL run with its working directory outside the project, without the user site, without bytecode
writing and with neither the working directory nor an inherited `PYTHONPATH` on the interpreter's path, so
no target-repo code runs. A language server
that cannot start, is not patched, fails or exits during the refactor SHALL make `dr-refactor` print the
`refactor.pyright-failed` finding on stderr followed by its cause, as "A failed checker's cause is printed" describes,
write nothing and exit 1. With or without `--apply`, the language server SHALL create no file in the project.

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

#### Scenario: Undecodable file
- **WHEN** `pkg/a.py`'s `foo` is renamed and `pkg/b.py` starts with `# coding: nosuch` and imports and calls `foo`
- **THEN** `pkg/b.py` is unchanged, stderr lists `refactor.undecodable` for `pkg/b.py`, and the exit code is 0

#### Scenario: Language server failure
- **WHEN** the language server cannot start or exits during the rename, with or without `--apply`
- **THEN** stderr is the `refactor.pyright-failed` finding followed by its cause, the exit code is 1 and every file of
  the project is unchanged

#### Scenario: No target-repo code runs
- **WHEN** the project's root holds a `sitecustomize.py` that writes a marker file when imported, and a rename runs
- **THEN** the marker file does not exist afterwards

#### Scenario: Dry-run leaves the tree unchanged
- **WHEN** a rename that adds basedpyright references runs without `--apply`
- **THEN** every path under the project is byte-identical before and after, and no new path exists

#### Scenario: Module renamed onto an existing module
- **WHEN** module `pkg/a.py` is renamed to `b`, in one project where `pkg/b.py` exists, in another where a package
  `pkg/b/` exists, and in a third where `pkg/__init__.py` binds `b`
- **THEN** each rename is refused with the name-conflict finding naming `pkg/b.py` line 1, `pkg/b/__init__.py` line
  1 and the binding's line respectively, stderr is `[resolve]`, `[checks]` and that finding, and nothing changes

#### Scenario: Module rename capturing an importer's name
- **WHEN** module `pkg/a.py` is renamed to `b`, no module `b` exists, and `pkg/use.py` holds `from pkg import a` and
  binds its own `b`
- **THEN** the rename is refused naming the line of `pkg/use.py`'s `b`

#### Scenario: Relative import of a renamed module
- **WHEN** module `pkg/a.py` is renamed to `b` and `pkg/use.py` holds `from . import a` with no `b` of its own
- **THEN** the import becomes `from . import b` and the exit code is 0

#### Scenario: Alias spelled like the module
- **WHEN** module `pkg/sql/client.py` is renamed to `cli2`, `tests/a.py` holds `import pkg.sql.client as client` and
  `client.X`, and `tests/b.py` holds `from pkg.sql import client as sql_client` and `sql_client.X`
- **THEN** `tests/a.py` becomes `import pkg.sql.cli2 as cli2` and `cli2.X`, and `tests/b.py` becomes
  `from pkg.sql import cli2 as sql_client` with `sql_client.X` unchanged

#### Scenario: Package rename
- **WHEN** package `pkg/sql/` (with an `__init__.py`) is renamed to `db` and modules import `pkg.sql.engine` and
  `from pkg import sql`
- **THEN** the directory moves to `pkg/db/` and every such import and use names `db`

#### Scenario: Moved-module stub
- **WHEN** `pkg/a.py` is renamed to `b` with `--stub 2.0` and the stub is `raise_moved("{old}", "{new}", removal="{removal}")`
- **THEN** `pkg/b.py` holds the module and `pkg/a.py` holds `raise_moved("pkg.a", "pkg.b", removal="2.0")`

#### Scenario: Stub refused
- **WHEN** `--stub` comes with a symbol rename, a package rename, the rename of a library module's alias, or no
  configured stub
- **THEN** stderr is `[resolve]`, `[checks]` and the finding, the exit code is 2 and nothing changes

#### Scenario: Module rename keeps line endings
- **WHEN** a module renamed by a module rename is imported from a file whose lines end in a mix of CRLF and LF
- **THEN** only the module's spelling changes and every line keeps its own ending

### Requirement: Python async definitions rename like sync ones
The Python `dr-refactor rename` SHALL rename an `async def` method or function located by `--line`/`--col`,
`--offset` or `--symbol`, at its definition or at a call: its definition, its overrides in the renamed hierarchy
and every call it would rename for the same code without `async`.

#### Scenario: Async method from its definition
- **WHEN** `class A` has `async def get_model(self, x: int) -> None: ...`, `class B(A)` overrides it with an `async
  def`, and a function holds `a = A()` and `await a.get_model(1)`, and the rename names `get_model` in `A` by
  `--line`/`--col`
- **THEN** both definitions and the call are renamed and the exit code is 0

#### Scenario: Async function from a call
- **WHEN** a module-level `async def fetch()` is renamed by `--offset` of one of its calls
- **THEN** the definition and every call are renamed

#### Scenario: Async method by path
- **WHEN** the same method is renamed by `--symbol A.get_model`
- **THEN** the result equals the `--line`/`--col` rename

### Requirement: Python rename refusals are findings
When an entry's location is not an identifier, names nothing Python's scoping rules or the checker resolve, or its new
name is a Python keyword, the Python `dr-refactor` SHALL report the `refactor.cannot-rename` finding for that entry on
stderr, write nothing and exit 1. No traceback or library message text SHALL be printed.

#### Scenario: Location that is not an identifier
- **WHEN** `rename --offset` points at whitespace between two statements
- **THEN** stderr ends with the `refactor.cannot-rename` finding and the exit code is 1

#### Scenario: Keyword as the new name
- **WHEN** `rename --symbol foo --new-name class` runs
- **THEN** stderr ends with the `refactor.cannot-rename` finding, the exit code is 1 and no file changes

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
- **THEN** stderr ends with the `refactor.name-conflict` finding naming that file and line, the exit code is 1 and no file
  changes

### Requirement: Python field renames refuse an unresolved owner chain
When the renamed symbol is a field of a class whose chain of bases holds a base basedpyright cannot resolve, the
Python `dr-refactor` SHALL print the `refactor.unresolved-base` finding naming the class, the file and the line of that
base, write nothing and exit 1. A rename of a class, function, method or module SHALL NOT be refused for this reason.

#### Scenario: Pydantic not resolvable
- **WHEN** the project's interpreter does not have `pydantic` and a field of `class Model(BaseModel)` is renamed
- **THEN** stderr ends with the `refactor.unresolved-base` finding naming `Model` and the line of its base, the exit code is
  1 and no file changes

#### Scenario: Method rename proceeds
- **WHEN** a method of the same class is renamed
- **THEN** the rename proceeds and exits 0

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

### Requirement: Python parameter renames cover every parameter kind
The Python `dr-refactor rename` SHALL rename a `def` or `async def` parameter of any kind (positional-only,
positional-or-keyword, keyword-only, `*args`, `**kwargs`) located by `--line`/`--col`, `--offset` or `--symbol`, at
its declaration, at a use in its function or at a `name=` keyword of a call. It SHALL rewrite each renamed
declaration, every use of it in its function including nested scopes, and every `name=` keyword at a call the
checker resolves to a renamed declaration. A `name=` keyword SHALL resolve only to a positional-or-keyword or
keyword-only parameter, never to a positional-only parameter, `*args` or `**kwargs`. Positional arguments, keywords
that reach the function unresolved (`**mapping` unpacking, `**kwargs` forwarding) and every other text SHALL be
unchanged.

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
A parameter rename SHALL be refused, as the requirement that renames keep every reference's binding defines, when a
name in the signature or the body of a function of any renamed declaration would resolve to another declaration: a
parameter or local of the new name, a read of a global or enclosing name of the new name, or a nested scope reading
the renamed parameter while binding the new name. `dr-refactor` SHALL then print the `refactor.name-conflict` finding
naming the first such site by project-relative path and then by character offset, with its file and line, write
nothing and exit 1. Attribute names (`x.new`), keywords of calls to other functions and a nested scope that binds the
new name without reading the renamed parameter SHALL NOT count. A rename to the old name SHALL succeed as a rename
with no edits.

#### Scenario: Duplicate parameter
- **WHEN** `def g(*, model_name: str, dataset_name: str) -> str` has `model_name` renamed to `dataset_name`
- **THEN** stderr ends with the `refactor.name-conflict` finding naming `dataset_name`, the file and the line of `g`'s
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

#### Scenario: Nested binding that captures nothing
- **WHEN** `def g(*, model_name: int) -> int` holds a nested `def inner[dataset_name]() -> None: ...` that does not
  read `model_name`, and `model_name` is renamed to `dataset_name`
- **THEN** the rename proceeds and exits 0

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
- **THEN** stderr ends with the `refactor.cannot-rename` finding, the exit code is 1 and no file changes

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

### Requirement: Member renames refuse on unclassified stand-ins
The renamed hierarchy SHALL be every declaration the rename renames with hierarchy on (Python: every member
declaration of OLD whose roots meet the located declaration's roots, where the roots of a declaration in class `C`
are the roots of OLD's declaration in each direct base of `C` that has OLD as the checker resolves it, or the
declaration itself when no direct base has OLD; TypeScript: the declarations
the language service's rename returns, merged interface declarations included), whether or not `--no-in-hierarchy` is
given, joined with the hierarchy of every `--with` stand-in. A stand-in SHALL be a class (Python) or a class,
interface or type literal (TypeScript), declared in a project source file of the rename's language and outside the
renamed hierarchy, that declares a member named OLD. Object literals SHALL NOT be stand-ins.

A member rename with any stand-in that is neither `--with` nor `--without` SHALL print one `refactor.stand-in` line
per stand-in member declaration on stderr, sorted by path, line and column and after any blind-spot lines, print
nothing on stdout, write nothing and exit 1, with or without `--apply`.

`--with PATH:LINE` and `--without PATH:LINE` (each repeatable, a relative PATH resolved against `--project`) SHALL
classify every stand-in member declared on that
line, together with that stand-in's own hierarchy. A `--with` stand-in SHALL be renamed in the same run: its
hierarchy joins the renamed hierarchy, and every rule of the rename (references, keyed rewrites, string-member
forms, `--docs`, `--keep`, blind spots) SHALL run once over the joined set, on one snapshot of the files, identical
edits merged. A `--without` stand-in SHALL be unchanged. A `--with` or `--without` naming no existing file or line
SHALL print `refactor.site-missing` in the `checks` phase. One whose line holds no stand-in member declaration of this
rename SHALL print `refactor.not-stand-in` at site resolution, which stops the run: nothing is written and the exit
code is 2. A module rename, in either language, has no stand-ins: when every entry of the run is a module rename, each
`--with` and `--without` site SHALL print `refactor.not-stand-in` in the `checks` phase; otherwise the sites SHALL be
classified by the run's other entries as above.
A TypeScript stand-in member declared by a computed name SHALL be classified by `--without` like any other;
`--with` naming its line SHALL print `refactor.computed-stand-in` at site resolution, write nothing and exit 2.

#### Scenario: Cast stand-in refuses until classified
- **WHEN** `StorageBackend.get_model` is renamed and `class _ModelReadCache` (no base in the hierarchy) defines
  `get_model` and is used as `cast(StorageBackend, _ModelReadCache(...))`
- **THEN** stderr holds, once, the `refactor.stand-in` line naming `_ModelReadCache.get_model` with its path and
  line, the exit code is 1 and no file changes

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
- **WHEN** `--with` names an existing line that declares no stand-in member of this rename
- **THEN** stderr holds the `[rules]` lines and no `[conflicts]` line, the final report holds `refactor.not-stand-in`
  naming that site, the exit code is 2 and no file changes

#### Scenario: Classification site on a Python module rename
- **WHEN** a Python module rename passes `--with pkg/use.py:3`
- **THEN** stderr is `[resolve]`, `[checks]` and `refactor.not-stand-in` naming `pkg/use.py:3`, no `[references]`
  line is printed, the exit code is 2 and no file changes

#### Scenario: Classification site on a TypeScript module rename
- **WHEN** a TypeScript module rename passes `--with src/use.ts:3`
- **THEN** stderr is `[resolve]`, `[checks]` and `refactor.not-stand-in` naming `src/use.ts:3`, the exit code is 2 and
  no file changes

#### Scenario: Classification site on a map with a module entry
- **WHEN** a map renames module `pkg/a.py` and method `A.save`, and passes `--without` the line of a stand-in
  declaring `save`
- **THEN** the stand-in is classified, `A.save`'s hierarchy and the module are renamed and the exit code is 0

#### Scenario: Two stand-ins on one line
- **WHEN** one line declares two stand-in members named OLD and `--without` names that line
- **THEN** both are classified and neither is reported

#### Scenario: Hierarchy flag off
- **WHEN** `A.run` is renamed with `--no-in-hierarchy` and `B(A)` overrides `run`
- **THEN** `B` is not reported as a stand-in

#### Scenario: Python diamond and mixin hierarchy
- **WHEN** `A.run` is renamed, `B(A)` and `C(A)` override `run`, `D(B, C)` overrides it, and an unrelated mixin
  `M` declaring `run` is a base of `E(M, A)`
- **THEN** `A.run`, `B.run`, `C.run` and `D.run` are renamed, and `M.run` is reported as a stand-in

#### Scenario: TypeScript structural class and object literal
- **WHEN** interface `Store.getModel` is renamed, `class Fake { getModel() {} }` does not implement `Store`, and an
  untyped constant holds `{ getModel() {} }`
- **THEN** `Fake.getModel` is reported as a stand-in and the object literal is not

#### Scenario: Computed-name stand-in
- **WHEN** interface `Store.getModel` is renamed and `class Keyed { [KEY]() {} }` declares it through
  `const KEY = 'getModel'`
- **THEN** `Keyed.getModel` is reported as a stand-in; `--without` its line classifies it, and `--with` its line
  prints `refactor.computed-stand-in` at site resolution, writes nothing and exits 2

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
`dr-refactor rename` SHALL accept `--keep PATH[:LINE]` (repeatable). A relative PATH SHALL be resolved against
`--project` to a real path under the project, in every check and use; a directory SHALL match the files under it by whole path components.
Every edit the rename would make on a kept line, in a kept file or under a kept directory SHALL be dropped,
whichever rule produced it, and a blind spot there SHALL NOT block the rename. A `--keep` naming no existing file,
directory or line SHALL print `refactor.site-missing` in the `checks` phase, and a line keep whose line holds no old
name SHALL print `refactor.keep-unmatched` there (see the cheap checks).

At site resolution, a keep that matched no edit and no blind spot SHALL be decided by its form:
- a whole-file or directory keep (no `:LINE`) leaves the outcome as asked: it SHALL print `refactor.keep-unneeded`
  naming it on stderr, and the run SHALL go on and, with `--apply`, write;
- a line keep SHALL be refused, with `refactor.keep-unmatched-near` naming the edited line of its file nearest to the
  kept line, else `refactor.keep-unmatched` when its file holds no edited line. An edited line is the start line of
  an edit the run writes, after every keep is applied; of two edited lines equally near, the earlier SHALL be named.
  Every such keep SHALL be reported, nothing SHALL be written and the exit code SHALL be 2.

Keeping a declaration SHALL NOT keep its references.

A whole-file keep of a module file a module rename moves, in either language, or a keep naming the directory of a Python
package it moves, SHALL drop that move and every edit in that file or under that directory, and SHALL count as matched;
a directory keep SHALL also drop the moves of the modules and packages under it. A module whose own move is kept SHALL
still move with a package another entry moves, under its old name. In a `rename-map`, every keep SHALL be resolved
once, over every entry's final edits and moves.

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

#### Scenario: Unneeded file keep
- **WHEN** a rename runs with `--apply` and `--keep src/compat.py`, a file spelling the old name where no edit and no
  blind spot of the rename lands
- **THEN** stderr holds `refactor.keep-unneeded` naming `src/compat.py` after the last `[rules]` line and before
  `[conflicts]`, the rename is written and the exit code is 0

#### Scenario: Unneeded directory keep
- **WHEN** a rename runs with `--apply` and `--keep tests/compat`, a directory whose files hold no edit and no blind
  spot of the rename
- **THEN** stderr holds `refactor.keep-unneeded` naming `tests/compat`, the rename is written and the exit code is 0

#### Scenario: Unmatched keep
- **WHEN** `--keep src/a.py:9` names a code line spelling the old name where no edit of the rename lands, and the
  rename edits `src/a.py` on lines 4 and 12
- **THEN** stderr holds no `[conflicts]` line and ends with `refactor.keep-unmatched-near` naming `src/a.py:9` and
  line 12, the exit code is 2 and no file changes

#### Scenario: Unmatched line keep in a file without edits
- **WHEN** `--keep src/b.py:3` names a code line spelling the old name, and the rename edits nothing in `src/b.py`
- **THEN** stderr ends with `refactor.keep-unmatched` naming `src/b.py:3`, the exit code is 2 and no file changes

#### Scenario: Kept module file
- **WHEN** a Python module `pkg/old.py` is renamed with `--keep pkg/old.py`
- **THEN** the checks pass, the module is not moved and no `refactor.keep-unneeded` is printed

#### Scenario: Kept TypeScript module file
- **WHEN** a TypeScript module `src/a.ts` is renamed with `--keep src/a.ts`
- **THEN** the checks pass, the module is not moved, its importers are rewritten and no `refactor.keep-unneeded` is
  printed

#### Scenario: Kept importer line of a TypeScript module
- **WHEN** `src/a.ts` is renamed to `b` with `--keep src/use.ts:1`, where line 1 imports `./a.js`
- **THEN** the checks pass, line 1 is unchanged and every other importer reads `./b.js`

#### Scenario: Kept moved package
- **WHEN** a Python package `pkg/old/` is renamed with `--keep pkg/old`
- **THEN** the package is not moved, no `refactor.keep-unneeded` is printed and the exit code is 0

#### Scenario: Kept module inside a moved package
- **WHEN** a map renames package `pkg/sql/` to `db` and module `pkg/sql/client.py` to `cli`, with `--apply` and
  `--keep pkg/sql/client.py`
- **THEN** the module ends at `pkg/db/client.py` unchanged, its importers name `pkg.db.cli` (a kept move leaves its importers rewritten, as for a single rename), and the exit code is 0

#### Scenario: Kept package around a moved module
- **WHEN** the same map runs with `--apply` and `--keep pkg/sql` instead
- **THEN** no file under `pkg/sql/` moves or changes, no `refactor.keep-unneeded` is printed, and the exit code is 0

#### Scenario: Keep relative to the project
- **WHEN** `dr-refactor --project proj rename ... --keep pkg/a.py:7` runs from the directory holding `proj`, where
  line 7 of `proj/pkg/a.py` holds a reference
- **THEN** that line is unchanged, every other reference is renamed and the exit code is 0; an absolute path naming
  the same line keeps it too

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

### Requirement: Symbols are located by their path in a file
`dr-refactor rename`, `retarget` and `move-symbol` SHALL accept `--symbol Q`, the path of a declaration inside
`--file`, in both languages. Q SHALL be segments joined by `.`, where `<locals>` steps into a function's body, a
trailing `(param)` names a parameter of the function the path names, and a trailing `['value']` or `["value"]`
names the member `value` of a string-literal type in the annotation or alias body of the declaration the path
names. At most one of `--offset`, `--line` and `--symbol` SHALL be given (a usage error, exit 2, otherwise).

The declarations a path SHALL reach are, in Python: module-level names (def, class, assignment, import binding),
class-body names (def, property, class, assignment, annotated field), `self.NAME` assignments in the class's methods
(as `Class.NAME` when the class body does not declare NAME), function locals and parameters; in TypeScript:
top-level functions, classes, interfaces, type aliases, enums, namespaces and variables, the members of a class,
interface, type literal (through an alias of it), enum or namespace, the locals of a function, method or
arrow-function body, and parameters.

Declarations the checker resolves to one symbol (overloads, property accessors, redefinitions in one scope, merged
TypeScript declarations) SHALL be one symbol, located at the first. A path that resolves to no declaration SHALL
exit 2 with `refactor.symbol-unresolved`, listing the names its deepest resolved scope declares; a path that
resolves to declarations of more than one symbol SHALL exit 2 with `refactor.symbol-ambiguous`, listing each
candidate's `path:line`. `move-symbol --symbol` SHALL accept only a top-level declaration.

#### Scenario: Method by path
- **WHEN** `rename --file src/pkg/storage.py --symbol StorageBackend.get_model --new-name load_model` runs
- **THEN** the result equals the same rename located by `--line`/`--col` at the method's name

#### Scenario: Nested function, parameter and field
- **WHEN** paths `build.<locals>.inner`, `StorageBackend.get_model(model_name)` and `_ProjectionPlan.measures`
  are renamed in turn
- **THEN** each renames that declaration and its references, and never a same-named declaration elsewhere in the
  file

#### Scenario: Instance attribute by class path
- **WHEN** `class C` assigns `self.cache = {}` in `__init__` and its body declares no `cache`, and `--symbol C.cache`
  is renamed
- **THEN** the assignment and every reference the checker resolves to it are renamed

#### Scenario: Import binding
- **WHEN** `--symbol Engine` names `from pkg.engine import Engine` in an importing file
- **THEN** the rename equals the rename located at the class declaration

#### Scenario: Overloads and accessors are one symbol
- **WHEN** a path names a function with `@overload` signatures, or a property with a setter
- **THEN** it is located without an ambiguity finding and every declaration is renamed

#### Scenario: Unresolved path lists candidates
- **WHEN** `--symbol StorageBackend.get_modle` runs and `StorageBackend` declares `get_model` and `save_model`
- **THEN** stderr ends with `refactor.symbol-unresolved` listing `get_model, save_model`, the exit code is 2 and nothing
  changes

#### Scenario: Ambiguous path lists candidates
- **WHEN** a module defines `class C` twice and `--symbol C.run` runs
- **THEN** stderr ends with `refactor.symbol-ambiguous` listing both `path:line` sites and the exit code is 2

#### Scenario: Two locators refused
- **WHEN** `--symbol foo --line 3` are both given
- **THEN** it exits 2 as a usage error

#### Scenario: TypeScript member and local by path
- **WHEN** `--symbol Store.getModel`, `--symbol build.<locals>.inner` and `--symbol Kind['edit_model']` run in
  TypeScript
- **THEN** each locates that declaration, through either invoking twin

### Requirement: Rename maps apply many renames as one
`dr-refactor rename-map MAP` SHALL read MAP (a path relative to the working directory) as a YAML list of entries
valid against the shared rename-map schema: either `file` relative to `--project`, exactly one locator (`symbol`,
`line` with an optional `col`, or `offset`), and exactly one of `new_name` or `retarget` (a `symbol` in the same file);
or a module entry, `module` (a source file relative to `--project`) and `new_name`, and nothing else. An
invalid map SHALL exit 2 with `refactor.map-invalid` naming every invalid entry's index, in index order, printed by
the invoking twin before any routing; a map that cannot be read or is not a non-empty list SHALL name entry 1. It SHALL
take `rename`'s options other than the locator and `--new-name`, applying to every entry. All entries SHALL be of one
language, else exit 2 with `refactor.map-mixed-languages`; the map runs in that language's twin.

Every locator SHALL be resolved against the code before any entry is computed, so entries name old names. A module
entry SHALL rename the module its file is, exactly as `rename --file` with no locator does: in Python, a package's
`__init__.py` naming the package, and a module entry and an entry located on an import of the same module SHALL resolve
to one symbol; in TypeScript, the one file, as the TypeScript module-rename requirement defines, and two module entries
naming one file SHALL resolve to one symbol. A module rename, by a module entry or by a locator on a Python import,
SHALL be computed beside any other entries. Two entries resolving to one symbol with the same intent SHALL merge; with
different intents they SHALL be refused with `refactor.map-duplicate` naming both entry indexes, exit 2. Every entry
SHALL then be computed on one snapshot of the project, every rename rule running once over the union of the entries'
symbols, with one blind-spot scan for every member entry's old name and each refusal reported once (see the
one-report requirement). A site any entry rewrites SHALL NOT be listed as another entry's leftover. Identical edits SHALL merge;
every site two entries rewrite differently SHALL be refused with `refactor.map-conflict` naming the site and both
entries, exit 1, writing nothing. Name conflicts SHALL be checked once, over all entries' edits together, on the code after the whole map: a
declaration another entry renames away SHALL NOT hold its old name, so a chain or a swap of symbol names (members,
parameters, locals, top-level names) applies, in any entry order, and entries that meet on one name or capture each
other's references are refused. A Python renamed keyword or key meeting its new name in one call or literal SHALL be
judged on the names after every entry's edits. When any site is refused with `refactor.map-conflict`, no
name-conflict check SHALL run. A `--with` stand-in that entries with different new names reach SHALL get each such
entry's rewrite, at its declaration and at every reference through it, so each of those sites is refused with
`refactor.map-conflict`, in both twins. A retarget
entry's rewritten references SHALL resolve to its target, which another entry may rename. A retarget entry whose
target another entry renames SHALL write the target's new name.

Every path the map prints (headers, diffs, findings) SHALL be a path before the map. A module rename's move SHALL be
printed as one `rename from`/`rename to` pair, from its old path to its new name beside it; an edit in a file that a
move moves SHALL be printed at the file's old path and, with `--apply`, written before the move. Moves inside a package
another entry moves SHALL compose: every project file SHALL end at the path its own move and every surviving move of
a package holding it produce, in any entry order, and the moves SHALL be made innermost first. The name-conflict
check SHALL see every surviving move composed, so two moves that end at one path, a moved module meeting a name another entry's edits bind in
its package, and a module's new name capturing a reference another entry rewrites are each refused with
`refactor.name-conflict`. A module entry's new name SHALL still be checked against the code before the map (see the
cheap checks), so a chain of module names is refused.

`rename` SHALL behave as a one-entry map with a `new_name`, and `retarget` as a one-entry map with a `retarget`;
their output SHALL equal that map's byte for byte. A `rename --file F --new-name N` with no locator SHALL be the
one-entry map `{module: F, new_name: N}`, in either language.

#### Scenario: Related renames in one pass
- **WHEN** a map renames `StorageBackend.get_model`, `StorageBackend.get_model_sync` and
  `StorageBackend.get_model(model_name)` and runs with `--apply`
- **THEN** stdout has one header line per entry in map order, one diff per changed file and the applied footer, and
  every reference of the three symbols is renamed

#### Scenario: Entries name old names
- **WHEN** a map renames method `A.old` to `new` and, in a later entry, parameter `A.old(x)` to `y`
- **THEN** both renames apply and the method is `new(self, y)`

#### Scenario: One combined refusal
- **WHEN** two member entries each meet one untyped receiver
- **THEN** each blind spot is printed once, under its group's `[rules]` line, the final report is one
  `refactor.blindspots` line, the exit code is 1 and nothing changes

#### Scenario: Duplicate entries
- **WHEN** two entries locate the same method with new names `a` and `b`
- **THEN** stderr ends with `refactor.map-duplicate` naming both entry indexes and the exit code is 2

#### Scenario: Conflicting edits
- **WHEN** one entry renames `Base.save` to `store` and another renames `Sub.save`, its override, to `keep`
- **THEN** stderr's final report holds `refactor.map-conflict` naming a shared site and both entries, the exit code is
  1 and nothing changes

#### Scenario: Swap in one scope refused
- **WHEN** a map renames module `pkg/a.py` to `b` and module `pkg/b.py` to `a`
- **THEN** stderr is `[resolve]`, `[checks]` and the `refactor.name-conflict` finding of each entry, the exit
  code is 1 and nothing changes

#### Scenario: Swap of symbol names applies
- **WHEN** a map renames parameter `f(x)` to `y` and `f(y)` to `x` and runs with `--apply`
- **THEN** both renames apply, every read of each parameter follows it, and the exit code is 0

#### Scenario: Chain of member names
- **WHEN** a map renames `Q.metrics` to `legacy_metrics` (TypeScript `legacyMetrics`) and `Q.measures` to `metrics`,
  in either entry order, and runs with `--apply`
- **THEN** both renames apply, a call `q.measures() + q.metrics()` becomes `q.metrics() + q.legacy_metrics()`, and
  the exit code is 0

#### Scenario: Chain and swap of each symbol kind
- **WHEN** maps chain and swap two parameters of one function, two locals of one function and two top-level names
  of one module, in either entry order
- **THEN** each map applies and the exit code is 0

#### Scenario: Chain whose freed declaration is kept
- **WHEN** the member chain runs with `--keep` on the line declaring `Q.metrics`
- **THEN** the checks pass, and the map is refused in `conflicts` with the `refactor.name-conflict` finding of the
  entry renaming `Q.measures`, naming the kept line; nothing changes and the exit code is 1

#### Scenario: Stand-in two entries reach
- **WHEN** a map renames `Table.columns` to `fields` and `Result.columns` to `result_columns`, a third class
  `Other` declares `columns` and a function reads it through `o: Other`, and the map passes `--with` the line of
  `Other.columns`
- **THEN** stderr's final report holds `refactor.map-conflict` naming entries 1 and 2 for the declaration's line and
  for the read's line, through either twin, the exit code is 1 and nothing changes

#### Scenario: Map conflict without a name check
- **WHEN** two entries rewrite one site differently and a third entry's new name would capture a reference
- **THEN** the final report holds the `refactor.map-conflict` finding and no `refactor.name-conflict` finding

#### Scenario: Two entries converging on one name
- **WHEN** a map renames parameter `f(x)` to `z` and `f(y)` to `z`
- **THEN** stderr is `[resolve]`, `[checks]` and the `refactor.name-conflict` finding of entry 2 naming the line of
  `f`, and nothing changes

#### Scenario: Two catch variables taking one name
- **WHEN** a TypeScript map renames the variables of two separate `catch` clauses to `err`
- **THEN** both renames apply and the exit code is 0

#### Scenario: Entries capturing each other's references
- **WHEN** one entry renames a module-level `a` to `z`, another renames a function's local `b` to `z`, and that
  function reads `a`, so that each entry alone is clean
- **THEN** the map is refused in `conflicts` with the `refactor.name-conflict` finding of the later entry, naming the
  line of `a`, and nothing changes

#### Scenario: Retarget beside a rename
- **WHEN** a map retargets alias `old_alias` to `target` and renames `target` to `renamed`, and a function reading
  `old_alias` binds no `renamed`
- **THEN** both entries apply and the function reads `renamed`

#### Scenario: Mixed languages
- **WHEN** a map holds a `.py` and a `.ts` entry
- **THEN** stderr is `refactor.map-mixed-languages` and the exit code is 2

#### Scenario: Invalid map
- **WHEN** entry 2 carries both `new_name` and `retarget`
- **THEN** stderr is `refactor.map-invalid` naming entry 2 and the exit code is 2

#### Scenario: Every invalid entry
- **WHEN** entries 2 and 4 are invalid
- **THEN** stderr is `refactor.map-invalid` naming entry 2 and then entry 4, through either invoking twin, and the
  exit code is 2

#### Scenario: Single rename equals its map
- **WHEN** `rename --file F --symbol Q --new-name N` and a map holding that one entry run on the same project
- **THEN** their stdout, stderr and exit codes are identical, through either invoking twin

#### Scenario: Another entry's rewrite is no leftover
- **WHEN** a map renames field `A.columns` to `fields` and `B.columns` to `cols`, and a file passes a
  `{"columns": ...}` dict to each class
- **THEN** each key is rewritten for its own class, no `leftover` line is printed and the exit code is 0

#### Scenario: Module entry beside symbol entries
- **WHEN** a map renames module `pkg/join_edges.py` to `relationship_edges` by `{module: pkg/join_edges.py}`, its class
  `JoinEdge` to `RelationshipEdge`, and function `pkg/use.py`'s `load` to `read`, where `pkg/use.py` holds
  `from pkg.join_edges import JoinEdge`, and runs with `--apply`
- **THEN** stdout holds the three headers in map order, the diff of `pkg/join_edges.py` at its old path, its `rename
  from`/`rename to` pair and the diff of `pkg/use.py`; `pkg/relationship_edges.py` declares `RelationshipEdge`,
  `pkg/use.py` holds `from pkg.relationship_edges import RelationshipEdge` and `def read`, and the exit code is 0

#### Scenario: TypeScript module entry
- **WHEN** a map renames `{module: src/join_edges.ts}` to `relationship_edges`, its class `JoinEdge` to
  `RelationshipEdge`, and function `src/use.ts`'s `load` to `read`, where `src/use.ts` holds
  `import { JoinEdge } from './join_edges.js'`, and runs with `--apply`
- **THEN** stdout holds the three headers in map order, the diff of `src/join_edges.ts` at its old path, its `rename
  from`/`rename to` pair and the diff of `src/use.ts`, whose import reads
  `import { RelationshipEdge } from './relationship_edges.js'`, and the exit code is 0

#### Scenario: Module entry located on an import
- **WHEN** a map renames function `pkg/use.py`'s `load` and, by a locator on `a` in `pkg/use.py`'s `import pkg.a`,
  module `pkg/a.py`
- **THEN** the function and the module are both renamed and the exit code is 0

#### Scenario: Two entries naming one module
- **WHEN** a map holds `{module: pkg/a.py, new_name: b}` and an entry located on `a` in `import pkg.a` with new name
  `c`; or `{module: pkg/sql/__init__.py, new_name: db}` and an entry located on `sql` in `import pkg.sql` with new name
  `db`
- **THEN** the first map is refused with `refactor.map-duplicate` naming both entries, and the second merges them into
  one rename of the package

#### Scenario: Two TypeScript entries naming one file
- **WHEN** a map holds `{module: src/a.ts, new_name: b}` twice, or `{module: src/a.ts, new_name: b}` and
  `{module: src/a.ts, new_name: c}`
- **THEN** the first map renames the module once with one header, and the second is refused with
  `refactor.map-duplicate` naming both entries

#### Scenario: A TypeScript map refused late writes nothing
- **WHEN** an `--apply` map renames module `src/a.ts` to `b` and function `src/use.ts`'s `load` to `read`, with a line
  keep that matches no edit
- **THEN** the run is refused with `refactor.keep-unmatched-near` or `refactor.keep-unmatched`, `src/a.ts` exists,
  `src/b.ts` does not, and every file is unchanged

#### Scenario: Specifier and imported name in one import
- **WHEN** a map renames module `src/a.ts` to `b` and its export `f` to `g`, and `src/use.ts` holds
  `import { f } from './a.js'`
- **THEN** the import reads `import { g } from './b.js'` and the exit code is 0

#### Scenario: A retarget's removed import meeting a module entry
- **WHEN** a TypeScript map retargets an alias so that an import of its target becomes a duplicate the retarget
  removes, and a module entry renames the module that import's specifier names
- **THEN** stderr's final report holds `refactor.map-conflict` naming that site and both entries, the exit code is 1
  and nothing changes

#### Scenario: Package and module inside it
- **WHEN** a map renames package `pkg/sql/` to `db` by `{module: pkg/sql/__init__.py}` and module
  `pkg/sql/client.py` to `cli`, in either order, and runs with `--apply`
- **THEN** stdout holds a `rename from pkg/sql`/`rename to pkg/db` pair and a `rename from pkg/sql/client.py`/`rename
  to pkg/sql/cli.py` pair, the module ends at `pkg/db/cli.py`, `import pkg.sql.client` becomes `import pkg.db.cli`,
  and the exit code is 0

#### Scenario: Three nested moves
- **WHEN** a map renames packages `pkg/` to `app`, `pkg/sql/` to `db` and module `pkg/sql/client.py` to `cli`
- **THEN** the module ends at `app/db/cli.py` and `from pkg.sql import client` becomes `from app.db import cli`

#### Scenario: Two module entries ending at one path
- **WHEN** a map renames package `pkg/a/` to `c` and module `pkg/b.py` to `c`, where no `c` exists yet
- **THEN** the map is refused with `refactor.name-conflict` and nothing changes

#### Scenario: A module meeting a binding another entry introduces
- **WHEN** a map renames module `pkg/a.py` to `b` and `pkg/__init__.py`'s function `x` to `b`
- **THEN** the map is refused with `refactor.name-conflict` naming `pkg/__init__.py` and nothing changes

#### Scenario: A chain of module names
- **WHEN** a map renames module `pkg/a.py` to `b` and module `pkg/b.py` to `c`, or module `src/a.ts` to `b` and module
  `src/b.ts` to `c`
- **THEN** stderr is `[resolve]`, `[checks]` and `refactor.name-conflict` naming `pkg/b.py` or `src/b.ts` line 1, the
  exit code is 1 and nothing changes

#### Scenario: Stubs for every moved module file
- **WHEN** a map renames modules `pkg/a.py` to `b` and `pkg/c.py` to `d` and function `pkg/e.py`'s `f` to `g`, with
  `--stub 2.0` and a configured stub
- **THEN** `pkg/a.py` and `pkg/c.py` hold the stub with their own old and new dotted names, and the exit code is 0

#### Scenario: Stub refused for a map holding a package or alias rename
- **WHEN** a map with `--stub 2.0` renames module `pkg/a.py` and either package `pkg/sql/` or the alias `np` of
  `import numpy as np`
- **THEN** stderr is `[resolve]`, `[checks]` and `refactor.stub-not-module`, the exit code is 2 and nothing changes

#### Scenario: Invalid module entries
- **WHEN** entry 1 holds `module` and `symbol`, entry 2 `module` and `retarget`, and entry 3 `module` and `file`
- **THEN** stderr is `refactor.map-invalid` naming entries 1, 2 and 3, through either invoking twin, and the exit code
  is 2

#### Scenario: Module rename equals its map
- **WHEN** `rename --file F --new-name N` and the map `[{module: F, new_name: N}]` run on the same project, for every
  module-rename case of the corpus in either language
- **THEN** their stdout, stderr and exit codes are identical

### Requirement: An apply writes every file or none
`dr-refactor --apply` SHALL re-check, immediately before writing, that no file it writes changed since it was read,
and SHALL write each file through a temporary file in the same directory renamed over it. When any write fails, the
files already written SHALL be restored, a finding SHALL be printed and the exit code SHALL be 1. When restoring a
file fails, the other restorations SHALL still be attempted and `refactor.rollback-failed` SHALL name every path left
changed; the exit code SHALL be 1.

#### Scenario: Failed write rolls back
- **WHEN** a map's apply fails while writing its third file
- **THEN** the first two files hold their original bytes and the exit code is 1

### Requirement: Refactors keep the type-check baseline aligned
Every `dr-refactor` subcommand SHALL keep the baseline of each language it edits aligned, when that language's
`commands.typecheck` entry is set and its `baseline_file` exists at the repo root and lists a file the refactor
affects. A baselined diagnostic that the refactor moves, by an edit on its line, a moved file or a moved
declaration, SHALL stay baselined; no diagnostic SHALL become baselined that was not. The baseline SHALL appear in
the printed diff in dry-run and `--apply` alike, and with `--apply` be written with the sources. Diagnostic ranges SHALL be mapped
through the refactor's edits: a start at or inside a replaced span SHALL map to the replacement's start, an end
inside or at the end of one to the replacement's end; at an insertion point a start SHALL map after the inserted
text and an end before it, and an empty range SHALL map both ends as its start.

- Python (`.basedpyright/baseline.json`): the baselined diagnostics and the entries they match SHALL be those
  basedpyright itself matches, from running the configured command over the affected files once with a temporary
  copy of the baseline and once with an empty one; the project's baseline SHALL NOT be written by the checker. Each
  matched entry whose file, columns or line count change SHALL be rewritten in place, or inserted at its sorted
  position in its new file. The configured command SHALL first be probed in the `checks` phase, run once on one source
  of the refactor, so a command that cannot run refuses before any reference search.
- TypeScript (`.tsc-baseline.json`): the before and after diagnostics SHALL be the pre-emit diagnostics, from the
  bundled language services of every project holding the file, of every file the baseline lists, before and after
  the edits applied in memory, keyed as `la-typecheck` keys tsc's output. A baselined key whose instances all map to
  one new key SHALL move its count there.

A diagnostic whose range cannot be mapped, or a TypeScript key whose instances map to different keys while only
some are baselined, SHALL leave its entry unchanged and print `refactor.baseline-ambiguous` on stderr, without
changing the exit code. A checker run that fails SHALL exit 1 with `refactor.baseline-failed` naming the language,
followed by the checker's cause, and write nothing.

#### Scenario: Rename shifts baselined columns
- **WHEN** a line holds a baselined `reportArgumentType` error after a call of `get_model`, and `get_model` is
  renamed to `load` with `--apply`
- **THEN** that entry's columns shift by the length difference, every other entry is unchanged, and `la-typecheck`
  passes afterwards

#### Scenario: Dry-run shows the baseline
- **WHEN** the same rename runs without `--apply`
- **THEN** the diff of `.basedpyright/baseline.json` is printed with the source diffs and nothing is written

#### Scenario: Matching follows basedpyright
- **WHEN** a file's baseline holds two identical-shaped entries, a stale entry, and an entry for a diagnostic below a
  newly unbaselined one, and a rename edits those lines
- **THEN** exactly the entries basedpyright matched are rewritten, and `la-typecheck` reports the same new errors
  as before the rename

#### Scenario: Configured command with a project flag
- **WHEN** `commands.typecheck.python` is `basedpyright -p .` and the rename edits a baselined line
- **THEN** the entry is realigned

#### Scenario: Moved module
- **WHEN** `move-module` moves `pkg/a.py`, which has baseline entries, into `pkg/sub/`
- **THEN** those entries are listed under `./pkg/sub/a.py` and `la-typecheck` passes

#### Scenario: Moved declaration
- **WHEN** `move-symbol` moves a function with a baselined error into another file that has entries of its own
- **THEN** the entry moves to the destination file at its sorted position

#### Scenario: TypeScript message names the symbol
- **WHEN** an unedited `src/c.ts` has a baselined `TS2322` whose message names type `Old`, and `Old` is renamed to
  `New`
- **THEN** the key's count moves to the message naming `New`, and real `tsc` reproduces that key

#### Scenario: Ambiguous split
- **WHEN** a TypeScript key has two instances, one baselined, whose messages change differently
- **THEN** the key is unchanged, stderr holds `refactor.baseline-ambiguous` naming it, and the exit code is 0

#### Scenario: No baseline
- **WHEN** the repo has no baseline file, or `commands.typecheck.python` is null
- **THEN** no checker runs, no `[baseline]` line is printed, and the output equals the rename without alignment

#### Scenario: Checker failure
- **WHEN** the configured command cannot run
- **THEN** stderr ends with `refactor.baseline-failed` naming `python` and its cause, the exit code is 1 and nothing
  is written

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

### Requirement: --docs lists compound names
With `--docs`, a rename, retarget or map SHALL list every declaration, in a project source file of its language,
whose name contains OLD as a word sequence, with one `refactor.compound` line per declaration, sorted with the other
leftovers; listing SHALL NOT change the exit code or the name. Names SHALL split into words at `_` and at CamelCase
boundaries (a run of capitals is one word), compared case-insensitively, the last word of OLD also matching with an
`s` or `es` suffix. OLD itself and every name the refactor renames SHALL NOT be listed.

#### Scenario: Compound names listed
- **WHEN** `Model` is renamed to `Dataset` with `--docs` and the project declares `ModelMeasures`, `AcmeModels`,
  `TestModelMeasurePosition`, `model_name` and `Modelling`
- **THEN** the first four are listed with `refactor.compound` and `Modelling` is not

#### Scenario: Snake case and plural
- **WHEN** `column` is renamed with `--docs` and the project declares `get_columns` and `ColumnCycleError`
- **THEN** both are listed

#### Scenario: Without --docs
- **WHEN** the same rename runs without `--docs`
- **THEN** no compound name is listed

### Requirement: dr-compliance --attr takes several names
`dr-compliance --attr` SHALL be repeatable. One scan SHALL report the blind spots of every given name, sorted by
path, line, column and then name, in both languages.

#### Scenario: Two names
- **WHEN** `dr-compliance --select attr-blindspot --attr get_model --attr save_model tests` runs where untyped
  receivers access both
- **THEN** both names' blind spots are reported in one sorted block and the exit code is 1

### Requirement: dr-mock-lint compares with a base branch
`dr-mock-lint` SHALL be a parsed command: positional paths and `--base BRANCH`; `--help` SHALL print its help and
exit 0. With `--base`, it SHALL compare with `origin/BRANCH` after the shared best-effort fetch, as
`la-affected-tests` does, exiting 2 only when `origin/BRANCH` does not resolve. It SHALL lint the given files as they
are and the same files at the base, read from git without checking anything out (paths mapped through git's rename
detection), and SHALL print only the findings whose count, keyed by path, template and parameters other than the
line, exceeds the base's. The exit code SHALL be 1 iff it prints a finding.

#### Scenario: Help
- **WHEN** `dr-mock-lint --help` runs through either twin
- **THEN** it prints the help and exits 0

#### Scenario: Only new findings
- **WHEN** `tests/test_a.py` has an unspec'd `Mock()` at the base and the change adds a second one and moves the
  first down by three lines
- **THEN** with `--base main` only the added one is printed and the exit code is 1

#### Scenario: Renamed file
- **WHEN** the change renames `tests/test_a.py` to `tests/test_b.py` without touching its findings
- **THEN** with `--base main` nothing is printed and the exit code is 0

#### Scenario: TypeScript at the base
- **WHEN** a TypeScript test's `vi.fn()` double was untyped at the base and stays so
- **THEN** with `--base main` it is not printed

### Requirement: Renames keep every reference's binding
A `rename`, and every `new_name` entry of a `rename-map`, SHALL be refused when the edits it would write change which
declaration a name resolves to. The check SHALL cover every identifier spelled with the old or the new name, in every
source file of the project, that the language resolves by scope: in TypeScript bare references, declaration names,
import and export specifiers' names (the imported and re-exported names included), shorthand property values and
type references, each resolved with the meaning (value, type or namespace) its position requires; in Python every name read and every binding (`def`,
`class`, parameters, import aliases, `global` and `nonlocal`, `except`, `match`, `for`, `with`, comprehension and
walrus targets, type parameters), names bound by a star import of a project module (its `__all__` when that is a
literal list or tuple, else its module-level names not starting with `_`), and the forward-reference strings the
rename rewrites, each read in its enclosing scope. Edits in comments, docstrings, prose files, string members,
`Literal` values, string dictionary keys and call keywords SHALL NOT take part. After the edits:
- every rewritten occurrence SHALL resolve to the declaration it resolved to before, under its new name;
- every other occurrence SHALL resolve to the declaration it resolved to before, a language builtin or global
  included;
- no renamed declaration SHALL share, under its new name, a scope and a meaning with another declaration;
- an occurrence left by `--keep` MAY resolve to nothing, and SHALL NOT resolve to a declaration other than its own.

The check SHALL judge the code after every entry's edits. A refused rename SHALL print, for each entry it refuses,
the `refactor.name-conflict` finding with that entry's new name and its first site, in the original code, by project-relative path and then character offset, among: an existing declaration of the new name
that a rewritten occurrence or a renamed declaration would meet; an existing occurrence whose declaration would
change; the declaration a kept occurrence would resolve to; and, when renamed declarations of two entries would meet,
the earliest entry's first declaration, as the latest entry's finding. It SHALL write nothing and exit 1. Name conflicts SHALL be checked after
`--keep` is applied and before the blind-spot and stand-in refusal. A rename to the old name SHALL succeed as a rename
with no edits.

#### Scenario: Reference captured by an inner binding
- **WHEN** `old` is renamed to `next` in a module holding `old = 1` (TypeScript `export const old = 1`) and a function
  that binds a local `next` and returns `old + next`
- **THEN** stderr ends with the `refactor.name-conflict` finding naming `next` and the line of the local `next`, the exit
  code is 1 and no file changes

#### Scenario: Name the declaring scope already binds
- **WHEN** a module-level `old` is renamed to `f` and the module defines a function `f`
- **THEN** the rename is refused naming the line of `f`

#### Scenario: Outer reference shadowed by the renamed declaration
- **WHEN** a module binds `nxt = 5` and a function binds a local `old2` and returns `old2 + nxt`, and `old2` is
  renamed to `nxt`
- **THEN** the rename is refused naming the line of the function's read of `nxt`

#### Scenario: Builtin shadowed
- **WHEN** a module-level `old` is renamed to `len` (TypeScript `parseInt`) and a function of the module calls `len`
  (`parseInt`)
- **THEN** the rename is refused naming the line of that call

#### Scenario: Importer already binds the new name
- **WHEN** `old` in `m` is renamed to `next` and another module imports `old` from `m` directly and binds its own
  `next`
- **THEN** the rename is refused naming the line of the importer's `next`

#### Scenario: Re-export boundary in TypeScript
- **WHEN** `src/index.ts` re-exports `old` from `./m`, `src/use.ts` imports `old` from `./index` and binds its own
  `next`, and `old` in `src/m.ts` is renamed to `next` in a project where nothing else captures it
- **THEN** the re-export becomes `export { next as old }`, `src/use.ts` is unchanged and the exit code is 0

#### Scenario: Aliased import in TypeScript
- **WHEN** `src/m.ts` re-exports `./other` (which exports `next`) with `export *` and declares `old`, `src/use.ts`
  imports `next as n` from `./m`, and `old` is renamed to `next`
- **THEN** the rename is refused naming the line of `src/use.ts`'s import

#### Scenario: Re-export and star-import chains
- **WHEN** `old` in `a` reaches a module through two re-exports (Python: two star imports) and that module binds
  `next` and reads `old`
- **THEN** the rename to `next` is refused naming the first site the chain's last module would change

#### Scenario: Type and value meanings in TypeScript
- **WHEN** a constant `old` is renamed to `next` in a module declaring `type next = string`, and the module uses
  `next` only as a type and `old` only as a value
- **THEN** the rename proceeds and exits 0

#### Scenario: Declaration merging in TypeScript
- **WHEN** an interface `Old` is renamed to `Next` in a module declaring a class `Next`
- **THEN** the rename is refused naming the line of the class

#### Scenario: Overloads renamed as one
- **WHEN** a TypeScript function with two overload signatures and its implementation, or a Python function with an
  `@overload` group, is renamed to a free name
- **THEN** every declaration of the group is renamed and the exit code is 0

#### Scenario: Python scope rules
- **WHEN** a method binds a local named like a class-body attribute, a comprehension's first iterable reads an outer
  name, a walrus in a comprehension binds in the enclosing function, and functions declare `global` and `nonlocal`
  names, and renames to and from those names run
- **THEN** each rename is refused exactly when a name read by the code would resolve to another declaration, as
  Python itself resolves it

#### Scenario: Python class body reads before binding
- **WHEN** a class body reads `old` and binds `next` only after the read, and the module-level `old` is renamed to
  `next`
- **THEN** the rename proceeds and exits 0; it is refused when a binding of `next` may run before the read (earlier
  in the body, conditionally or not, or in a loop holding the read)

#### Scenario: Forward-reference string captured
- **WHEN** class `Old` is renamed to `Next` and a function that binds a local `Next` annotates a local with `"Old"`
- **THEN** the rename is refused naming the line of the local `Next`

#### Scenario: Kept site rebinding
- **WHEN** `--keep` leaves a reference to the inner `old` of a function, and an outer `old` exists
- **THEN** the rename is refused naming the line of the outer `old`

#### Scenario: Kept site dangling
- **WHEN** `--keep` leaves a reference to `old` and no other `old` is in reach
- **THEN** the rename proceeds, that reference is unchanged and the exit code is 0

#### Scenario: Kept declaration
- **WHEN** `--keep` leaves the declaration of `old` while its references are rewritten
- **THEN** the rename is refused naming the first rewritten reference

#### Scenario: No false conflict
- **WHEN** the new name is used only as an attribute (`o.next`), as a call keyword, in a comment, or as a local of an
  unrelated function, and a nested function binds its own `next` without reading `old`
- **THEN** the rename proceeds and exits 0

#### Scenario: Docs and literal members keep their own rules
- **WHEN** a rename with `--docs` rewrites a comment mentioning `old` beside a local `next`, and a `Literal` member
  rename writes a value equal to a local's name
- **THEN** neither edit counts as a conflict

### Requirement: Member renames refuse a name the member's namespace holds
A rename of a member (a method, property, field, accessor, enum member, class-body attribute, and in Python an
attribute assigned through `self` in a method of the class) SHALL be refused when a member of the new name that the
rename does not itself rename (its hierarchy, overload group and `--with` stand-ins) is declared on the same side by
a type holding a renamed declaration (a class, interface, type literal, enum or object literal), by any of its
ancestors (in the project or a library, the implicit root included) or by any of its descendants in the project. In
TypeScript the instance and static sides SHALL be separate and the root SHALL be `Object`'s apparent members; in
Python a class SHALL have one namespace, ancestors SHALL be its whole MRO and the root's members SHALL be those
`shared/languages.yaml` lists. Members added from outside the class or by `setattr` SHALL NOT count. The finding
SHALL be `refactor.name-conflict` naming the existing member's site, or the renamed declaration's own site when that
member is declared outside the project; it SHALL write nothing and exit 1.

#### Scenario: The class already declares the new name
- **WHEN** method `C.old` is renamed to `next` and `C` declares a method `next`
- **THEN** stderr ends with the `refactor.name-conflict` finding naming the line of `C.next`, the exit code is 1 and no
  file changes

#### Scenario: An ancestor or a descendant declares the new name
- **WHEN** `C.old` is renamed to `next` and, in one project, a base of `C` declares `next`, and in another a subclass
  of `C` does
- **THEN** each rename is refused naming that member's line

#### Scenario: A library base declares the new name
- **WHEN** `C.old` of `class C(dict)` (TypeScript `class C extends Array<number>`) is renamed to `keys` (`map`)
- **THEN** the rename is refused naming the line of `C.old`

#### Scenario: The implicit root declares the new name
- **WHEN** `C.old` is renamed to `__repr__` (TypeScript `toString`)
- **THEN** the rename is refused naming the line of `C.old`

#### Scenario: Static and instance sides in TypeScript
- **WHEN** instance method `C.old` is renamed to the name of a static method of `C`
- **THEN** the rename proceeds and exits 0

#### Scenario: One Python class namespace
- **WHEN** `C.old` is renamed to `next` and `C` assigns `self.next` in `__init__`, and in another project `C` declares
  a `classmethod` `next`
- **THEN** each rename is refused naming that member's line

#### Scenario: The renamed hierarchy is no conflict
- **WHEN** `Base.old` is renamed to `next`, `Sub(Base)` overrides `old`, an interface method `I.old` is renamed with
  its implementation `C.old`, and a class inherits `old` from two bases that both declare it
- **THEN** each rename proceeds and exits 0

#### Scenario: Two map entries meeting on one member name
- **WHEN** a map renames TypeScript parameter property `C.a` and field `C.b` both to `x`
- **THEN** the map is refused naming the line of `C.a`

### Requirement: Retarget rewrites references to an alias and keeps every name bound
`dr-refactor retarget --file F --symbol ALIAS --target TARGET` (and a map entry with `retarget`) SHALL rewrite every
reference the rename of ALIAS to TARGET's name would rewrite, every rename rule included, except the edits at
ALIAS's own declarations and at re-export sites; ALIAS SHALL stay declared and unchanged. Checks that the new name is
already used SHALL NOT apply.

TARGET SHALL be a binding in the class body or module scope that declares ALIAS, where an import counts as a binding
(Python `from M import T` or `from M import X as T`; TypeScript `import { T } from 'M'` or `import { X as T } from
'M'`). Where ALIAS is itself declared by a re-export of an imported name (Python `from M import T as ALIAS`;
TypeScript `export { T as ALIAS } from 'M'`, or `import { T as ALIAS } from 'M'` exported as ALIAS), TARGET SHALL
name that imported name `T`. A member ALIAS SHALL have TARGET declared in its own class. Otherwise the retarget SHALL
exit 2 with `refactor.retarget-scope`. TARGET's home SHALL be the module ALIAS's module imports TARGET from, under the
name that module exports it by, or ALIAS's module where TARGET is declared there; the home SHALL NOT be followed
further along a re-export chain. TARGET's identity (its declarations, and the declarations an import of it resolves to
through any re-export chain) SHALL decide whether a name is bound to TARGET.

After the retarget, every rewritten reference SHALL name a binding of TARGET, in the meaning the reference needs (a
TypeScript type or value), on every path that reached ALIAS's binding:
- A bare name SHALL be rewritten to the local name of a binding of TARGET that dominates the statement binding ALIAS
  there; where none exists, the retarget SHALL import TARGET from its home at that statement. A bare name at which
  TARGET's written name is bound to something else SHALL refuse with `refactor.retarget-shadowed`, exit 1.
- An import of ALIAS from a module M (`from M import ALIAS [as Z]`, `import { ALIAS [as Z] } from 'M'`) SHALL become
  an import of TARGET from M, keeping `as Z`, where M exports TARGET (Python: declares it, lists it in `__all__`, or
  imports it `as` its own name; TypeScript: M's exports hold it); otherwise ALIAS SHALL leave that import and TARGET
  SHALL be imported from its home.
- A module attribute `MOD.ALIAS` (Python `import pkg.mod` or `from pkg import mod`; a TypeScript namespace import)
  SHALL be rewritten where MOD binds TARGET's name to TARGET at module level; otherwise it SHALL refuse with
  `refactor.retarget-unbound`, exit 1.

An added import of TARGET SHALL sit in the block of the statement binding ALIAS, joining that block's import from the
home when it precedes that statement, else replacing ALIAS's import in place when ALIAS was its only name, else as a
new statement right after it. Its module SHALL be spelled as the import it replaces or follows spells its own:
absolute or relative (Python), and in the same extension style (TypeScript), a package's module name for a Python
package; a TypeScript import of only type uses SHALL be type-only. One block SHALL get at most one import from one home,
however many entries of a map need it. An import of ALIAS SHALL stay while a reference it binds keeps ALIAS. Where
the rewrite would make an import of TARGET a duplicate of another import of TARGET in its block, the later of the two
SHALL be removed, so the module keeps its first import's place. A retarget whose TARGET another map entry renames SHALL
write and import TARGET's new name.

A re-export site SHALL stay unchanged: the `__all__` string naming ALIAS (`__all__` set by a plain, annotated or
augmented assignment, or by `.append` or `.extend`) and the module's import of ALIAS it re-exports; a TypeScript
`export { ALIAS }`, `export type { ALIAS }` or `export { ALIAS } from`, and the import it exports. Every other
reference in a re-exporting module, and every reference in a module importing ALIAS through it, SHALL follow the rules
above.

A member ALIAS SHALL refuse, exit 1 with one `refactor.retarget-override` line per site, while a class of its
hierarchy other than ALIAS's own declares ALIAS's name. A `refactor.retarget-shadowed` or `refactor.retarget-unbound`
refusal on a line `--keep` covers SHALL NOT block the retarget, and an import of TARGET serving only kept references
SHALL NOT be added.

#### Scenario: Method twin
- **WHEN** `class Engine` declares `save_model` and a deprecated `def save(self, m: Model) -> None: return
  self.save_model(m)`, code calls `engine.save(m)` with `engine: Engine`, and `retarget --symbol Engine.save
  --target Engine.save_model` runs
- **THEN** the call becomes `engine.save_model(m)` and `Engine.save` is unchanged

#### Scenario: Class twin and its imports
- **WHEN** `models.py` declares `AcmeModel = Model` and a module holds `from pkg.models import Model,
  AcmeModel` and uses `AcmeModel()`
- **THEN** after retargeting `AcmeModel` to `Model` the import is `from pkg.models import Model` and the use is
  `Model()`

#### Scenario: Imported target
- **WHEN** `compat.py` holds `from pkg.core import Model` and `AcmeModel = Model` with `__all__ = ["AcmeModel"]`,
  `use.py` holds `from pkg.compat import CONST, AcmeModel` and uses `AcmeModel()`, and `AcmeModel` is retargeted to
  `Model`
- **THEN** `compat.py` is unchanged, `use.py` holds `from pkg.compat import CONST` and `from pkg.core import Model` on
  the next line, and the use is `Model()`, in both languages

#### Scenario: Several aliases share one home import
- **WHEN** a map retargets `FlightCatalog` to `FacadeCatalog` and `FlightSchema` to `FacadeSchema`, both imported by
  the alias module from `pkg.facade`, and a module imports both aliases in one statement
- **THEN** that module gains one import from `pkg.facade` naming both targets

#### Scenario: Re-export form
- **WHEN** `compat.py` holds `from pkg.core import Model as AcmeModel` and `__all__ = ["AcmeModel"]`, and
  `retarget --symbol AcmeModel --target Model` runs
- **THEN** every module importing `AcmeModel` from `pkg.compat` imports `Model` from `pkg.core` instead, and
  `compat.py` is unchanged

#### Scenario: Other scope refused
- **WHEN** `class Engine` declares a deprecated `save` and `retarget --symbol Engine.save --target Store.save_model`
  runs
- **THEN** stderr ends with `refactor.retarget-scope` and the exit code is 2

#### Scenario: Overridden alias refused
- **WHEN** a subclass of `Engine` overrides `save`
- **THEN** stderr names that override with `refactor.retarget-override`, the exit code is 1 and nothing changes

#### Scenario: Shadowed target refused
- **WHEN** a function binds a local `Model` and uses `AcmeModel()` in its body
- **THEN** stderr names that use with `refactor.retarget-shadowed` and the exit code is 1

#### Scenario: Kept refusal does not block
- **WHEN** the shadowed use is on a line `--keep` names
- **THEN** that line is unchanged, every other reference is rewritten and the exit code is 0

#### Scenario: Re-export shim kept
- **WHEN** `compat.py` holds `from pkg.models import Model, AcmeModel` and `__all__ = ["Model", "AcmeModel"]`, and
  `AcmeModel` is retargeted to `Model`
- **THEN** `compat.py` is unchanged and a module's `from pkg.compat import AcmeModel` becomes `from pkg.compat import
  Model`, its uses `Model`

#### Scenario: Single-name shim and its importers rewritten
- **WHEN** `compat.py` holds `from pkg.models import AcmeModel`, `__all__ = ["AcmeModel"]` and `def make(): return
  AcmeModel()`, `use.py` imports `AcmeModel` from `pkg.compat`, and `AcmeModel` is retargeted to `Model`
- **THEN** `compat.py` keeps its import of `AcmeModel` and its `__all__`, imports `Model` from `pkg.models` and
  returns `Model()`, and `use.py` imports `Model` from `pkg.models` and uses `Model`

#### Scenario: Star import
- **WHEN** a module holds `from pkg.compat import *` from a single-name shim and uses `AcmeModel()` (TypeScript: it
  imports `AcmeModel` through an `export *` barrel)
- **THEN** the use becomes `Model()` and the module imports `Model` from `pkg.models` right after the star import

#### Scenario: Conditional and type-checking imports
- **WHEN** a module imports `AcmeModel` inside `if TYPE_CHECKING:`, inside `try:`, or inside a function, and uses it
  where that import binds it
- **THEN** `Model` is imported in that same block, and an import of `Model` in another block does not count as
  binding it

#### Scenario: Unbound module attribute refused
- **WHEN** a module holds `import pkg.compat` and uses `pkg.compat.AcmeModel()`, where `pkg.compat` does not bind
  `Model`
- **THEN** stderr names that use with `refactor.retarget-unbound` and the exit code is 1; with `--keep` on its line
  the retarget proceeds and the line is unchanged

#### Scenario: Bound module attribute rewritten
- **WHEN** a module uses `pkg.compat.AcmeModel()` where `pkg.compat` imports `Model`
- **THEN** the use becomes `pkg.compat.Model()`

#### Scenario: TypeScript merged alias
- **WHEN** a TypeScript class declares `/** @deprecated */ get old(): number { return this.value; }` and `value`,
  and `retarget --symbol C.old --target C.value` runs
- **THEN** every `c.old` read becomes `c.value` and the accessor is unchanged

#### Scenario: TypeScript type and value meanings
- **WHEN** `compat.ts` declares `export const Flight = Facade` and `export type Flight = Facade` of an imported
  `Facade`, and one importer uses `Flight` only as a type while another constructs `new Flight()`
- **THEN** the first imports `Facade` type-only and the second as a value, each from the home module

### Requirement: dr-refactor --timings prints each phase's wall time
`dr-refactor --timings` SHALL, for every subcommand and after all other output, print on stderr one
`refactor.timing` line per phase whose work ran at least once, in the order of the shared phase list (`load`,
`resolve`, `references`, `rules`, `conflicts`, `blindspot-scan`, `literal-scan`, `literal-probe`, `baseline`,
`write`), then one for `total`. A phase's time SHALL exclude the phases nested in it, and its repeated runs SHALL add
up. The time of the checks made over a run's computed edits (the sites two entries rewrite differently and every
name-conflict check) SHALL count under `conflicts` and under no other phase. The seconds SHALL be the elapsed time
floored to whole centiseconds, never negative, written as whole seconds, a dot and two digits. The lines SHALL be
printed on every exit once the arguments parse: success, a refusal or an error. A run handed to the other language's
twin SHALL print only that twin's lines; a run that exits before any phase ran (a routing or map error, or the other
twin missing) SHALL print only `total`. Without `--timings`, stdout, stderr and the exit code SHALL be unchanged.

#### Scenario: Line format
- **WHEN** a phase took 1.239 seconds and another 0.004 seconds
- **THEN** their lines read `timing: <phase> 1.23s` and `timing: <phase> 0.00s`

#### Scenario: Python Literal rename
- **WHEN** `dr-refactor --timings rename --file m.py --symbol "Kind['a']" --new-name b` runs
- **THEN** stdout is unchanged, and stderr ends with timing lines in list order that include `literal-scan` and
  `literal-probe`, then `total`

#### Scenario: TypeScript rename
- **WHEN** `dr-refactor --timings rename --file src/a.ts --symbol foo --new-name bar` runs
- **THEN** stdout is unchanged, and stderr ends with timing lines in list order, none of them a `literal-` phase,
  then `total`

#### Scenario: Conflict checks timed on their own
- **WHEN** `dr-refactor --timings rename-map map.yaml` runs a map that refuses nothing, in either twin
- **THEN** stderr holds a `conflicts` timing line after the `rules` line and before any `baseline` line

#### Scenario: Refusal still timed
- **WHEN** a member rename with `--timings` refuses on a blind spot
- **THEN** the exit code is 1, and the timing lines follow the refusal on stderr

#### Scenario: Forwarded run
- **WHEN** the npm twin runs `dr-refactor --timings rename --file m.py --symbol f --new-name g`
- **THEN** stderr holds the Python twin's timing lines once, and no line from the npm twin

#### Scenario: Exit before any phase
- **WHEN** `dr-refactor --timings rename-map map.yaml` runs on a map mixing `.py` and `.ts` entries
- **THEN** the map error is printed, then only the `total` timing line, and the exit code is 2

#### Scenario: Option absent
- **WHEN** any `dr-refactor` case of the corpus runs without `--timings`
- **THEN** its output equals its golden

### Requirement: Refactors run in announced phases and report their progress
Every `dr-refactor` subcommand SHALL run in the phases `resolve`, `checks`, `references`, `rules`, `conflicts`,
`baseline` and `write`, in that order, and SHALL print `refactor.progress-phase` on stderr when each phase starts. A
phase that does not run SHALL print nothing: `rules` runs for `rename`, `retarget` and `rename-map` unless every
entry is a module rename; `conflicts` runs for `rename`, `retarget` and `rename-map` when the run reaches the checks
made over its computed edits (the sites two entries rewrite differently and every name-conflict check), so not after a
`--fail-fast` stop and not after a refusing finding at site resolution; `baseline` runs when the refactor's language has its baseline file at the repo root and, for Python,
its `commands.typecheck` entry is set, whether or not anything is then realigned; `write` runs only with `--apply`.

Site resolution SHALL run once every entry's edits are final (every group's rules done, the imports retargets need
planned and every keep applied to the edits and the moves) and before
`conflicts`. It prints no phase line; its `refactor.keep-unneeded` lines SHALL be printed there, in command-line
order.

In `references`, `refactor.progress-item` SHALL be printed for each entry when its reference search starts, in map
order, an entry merged with a duplicate counting once: `n` its position, `count` the number of entries after
merging, `entries` every map index it stands for (`refactor.progress-entry` for one, `refactor.progress-entries` for
several), `new` its new name (a retarget's target name); a module rename's entry SHALL print its line like any other.
`move-symbol` and `move-module` print no per-entry lines.

In `rules`, the entries other than module renames SHALL be taken in groups of one old name, in the order of each
group's first entry. When a
group is done, its line SHALL be printed: `refactor.progress-clean` when it has no refusal of its own, else
`refactor.progress-refused` with the number of its refusals, followed by those refusal lines in path, line and column
order; a refusal printed there SHALL NOT be printed again. `count` SHALL be the number of groups, `entries` the group's map indexes and `new` its distinct new names in
map order, comma-separated. A group's refusals SHALL be counted after its sites under `--keep` are dropped. Refusals
between entries (map conflicts, name conflicts over the merged edits, site findings) SHALL appear only in the final
report.

`conflicts` SHALL print its phase line and no per-entry line.

Progress lines SHALL pass through forwarding to the other twin unchanged and in order.

#### Scenario: Phases of a clean map
- **WHEN** `dr-refactor rename-map map.yaml` runs a two-entry map that refuses nothing, without `--apply`, in a repo
  without a baseline file
- **THEN** stderr is `[resolve]`, `[checks]`, `[references]`, one `[references n/2]` line per entry, `[rules]`, one
  `clean` line per old-name group and `[conflicts]`, and stdout is the headers, the diffs and the dry-run footer

#### Scenario: A refused group prints its refusals as it finishes
- **WHEN** a map's second entry meets an untyped receiver and its first does not
- **THEN** the first group's line says `clean`, the second's says `1 refusal(s)` followed by the blind-spot line, and
  the final report is the `refactor.blindspots` line alone, exit code 1

#### Scenario: Unrelated entries sharing an old name
- **WHEN** a map renames two unrelated methods both named `save`, to `store` and `keep`
- **THEN** one `[rules 1/1]` line names `entries 1, 2`, `save -> store, keep`

#### Scenario: Merged duplicate entries
- **WHEN** entries 2 and 5 locate the same symbol with the same new name
- **THEN** one `[references]` line names `entries 2, 5` and `count` is one less than the number of map entries

#### Scenario: Apply phases
- **WHEN** a rename runs with `--apply` in a repo whose Python baseline file exists and checker command is set
- **THEN** stderr holds `[conflicts]`, then `[baseline]` and then `[write]` after `[rules]`

#### Scenario: Name conflict found in its phase
- **WHEN** a rename's new name is already bound where a renamed read resolves
- **THEN** stderr holds `[conflicts]` before the `refactor.name-conflict` finding, and the exit code is 1

#### Scenario: Module rename conflicts
- **WHEN** a Python module rename's edits change what a name means in an importer
- **THEN** stderr is `[resolve]`, `[checks]`, `[references]`, one `[references 1/1]` line, `[conflicts]` and the
  `refactor.name-conflict` finding, with no `[rules]` line

#### Scenario: Map of a module and a symbol
- **WHEN** a map renames a module and a function and refuses nothing
- **THEN** stderr holds one `[references n/2]` line per entry, `[rules]` with one line for the function's group, and
  `[conflicts]`

#### Scenario: No conflict phase after a fail-fast stop
- **WHEN** a map runs with `--fail-fast` and its first group refuses
- **THEN** stderr holds no `[conflicts]` line

#### Scenario: No conflict phase after a refusing site finding
- **WHEN** a map runs without `--fail-fast` and a line keep matches nothing
- **THEN** stderr holds every `[rules]` result line, no `[conflicts]` line and then the final report

#### Scenario: Warnings before the conflict phase
- **WHEN** a map runs with an unneeded file keep and nothing refuses
- **THEN** stderr holds the `[rules]` result lines, then `refactor.keep-unneeded`, then `[conflicts]`

#### Scenario: Move phases
- **WHEN** `move-module` runs without `--apply`
- **THEN** stderr is `[resolve]`, `[checks]`, `[references]` and no per-entry line

#### Scenario: Progress through the other twin
- **WHEN** a TypeScript rename runs through the PyPI twin
- **THEN** stdout, stderr and exit code equal the npm twin's own run

### Requirement: Cheap checks run before any reference search
Resolving every entry's locator SHALL search no references. Every resolution failure SHALL be collected with its entry
index, not stop the run: unresolved or ambiguous symbol paths, an out-of-range line, column or offset, a location that
cannot be renamed, a module rename's new name that cannot name a module (Python: no identifier, or a keyword;
TypeScript: as the TypeScript module-rename requirement defines) as `refactor.cannot-rename`, a retarget out of scope,
a literal value that cannot be written, a TypeScript file outside every project. Duplicate entries SHALL be found among
the resolved entries only. Each resolution failure SHALL be printed as `refactor.entry-refusal`, naming its
entry and locator (see the one-report requirement).

The `checks` phase SHALL then run, before any reference search:
- every `--keep`, `--with` and `--without` SHALL name, a relative PATH resolved against `--project`, an existing file
  or directory under the project, and a `:LINE`
  a line of an existing file, else `refactor.site-missing` naming the option and the site;
- every line keep (`--keep PATH:LINE`) SHALL name a line, in a file the run can edit (a source of its language, and
  with `--docs` a prose file), whose text holds an entry's old name or a retarget entry's target name, either as
  written (with identifier escapes decoded, and NFKC-normalized for Python) or in the value of a string literal
  starting on that line; or lie in a file the refactor moves; else `refactor.keep-unmatched`. Without `--docs`, a
  spelling inside a comment SHALL NOT count, except in a Python type comment (a comment whose text after `#` and
  optional whitespace starts with `type:`). When an entry that did not resolve spells no name in its locator, or an
  entry renames a `Literal` member, this check SHALL be skipped. A whole-file or directory keep SHALL get no check
  here beyond the site check;
- when every entry is a module rename, each `--with` and `--without` site SHALL be refused with
  `refactor.not-stand-in`;
- `--stub` SHALL be checked as the Python module-rename requirement defines, and refused in a TypeScript run as the
  TypeScript module-rename requirement defines;
- each module rename whose new name is already taken in the code before the refactor (Python: its package binds it, as
  the Python module-rename requirement defines; TypeScript: as the TypeScript module-rename requirement defines) SHALL
  be refused with `refactor.name-conflict`, exit 1;
- each `new_name` entry of a symbol other than a module SHALL be checked in the scope that declares it (a member:
  the type declaring it, in TypeScript on its own static or instance side; a parameter or local: its own scope; a
  top-level name: its module), and refused with `refactor.name-conflict`, exit 1, when that scope declares the new
  name and no other entry renames every such declaration to another name (naming the first such declaration), or
  when another entry renames a declaration of that scope to the same new name (the later entry's finding, naming the
  earlier entry's first declaration). This check SHALL refuse only what the name-conflict check over the computed
  edits would refuse: declarations that the language lets share a scope under one name (TypeScript declarations
  that merge or whose meanings are disjoint, overloads) SHALL NOT be refused; a pair SHALL be left to `conflicts`
  when a `--keep` covers the line of either declaration, or when the resolved entries do not decide whether the
  name is freed. Conflicts through inheritance, imports or references SHALL be found in `conflicts`;
- Python: for a move, every candidate file (a Python source whose text holds the moved name or module's name) SHALL be
  walked as `dr-compliance --select rope-walk` walks it, and each gap reported as `refactor.rope-walk`;
- Python: the language server SHALL start for `rename`, `retarget` and `rename-map` unless every entry is a module
  rename, or its occurrence index is cached and no entry renames a `Literal` member, and when the baseline phase will run, the configured checker SHALL run once on one source of the refactor; a failure SHALL be reported with its
  cause;
- in both twins, when the refactor's language has its baseline file at the repo root, the repo config SHALL be
  readable and valid, else its error SHALL be reported as the config loader words it, exit 2.

Each `--keep`, `--with` and `--without` argument SHALL get at most one finding; a failure in `checks` SHALL replace its
later exact check. When `resolve` or `checks` found anything, the run SHALL print nothing on stdout, print every
finding on stderr (resolution findings by entry index, site findings in command-line order, the `--stub` finding,
module and own-scope name conflicts by entry index, walker gaps by path, then checker findings), print no `[references]` line, write
nothing, and exit with the highest exit code of its findings.

#### Scenario: Missing keep path
- **WHEN** a rename passes `--keep src/gone.py`
- **THEN** stderr is `[resolve]`, `[checks]` and `refactor.site-missing` naming `--keep src/gone.py`, the exit code is
  2 and no file changes

#### Scenario: Keep line past the end
- **WHEN** `--keep src/a.py:99` names a line past the end of a 20-line file
- **THEN** stderr ends with `refactor.site-missing` naming `--keep src/a.py:99` and the exit code is 2

#### Scenario: Keep holding no old name
- **WHEN** `--keep architecture` names a directory whose files never spell the renamed name
- **THEN** the checks pass, `refactor.keep-unneeded` naming it is printed at site resolution and the exit code is 0

#### Scenario: Every bad keep at once
- **WHEN** a rename passes three keeps, one missing and two line keeps whose lines hold no old name
- **THEN** stderr lists all three findings in command-line order and the exit code is 2

#### Scenario: Comment-only line keep without --docs
- **WHEN** `--keep src/a.py:9` names a line whose only spelling of the old name is in a comment (a trailing comment
  or a line of a multi-line comment), without `--docs`
- **THEN** stderr ends with `refactor.keep-unmatched` naming `src/a.py:9`, no `[references]` line is printed and the
  exit code is 2

#### Scenario: Comment-only line keep with --docs
- **WHEN** the same keep runs with `--docs` and `--apply`, and the rename's `--docs` pass rewrites mentions of the old
  name in comments
- **THEN** the checks pass, every other mention is rewritten, line 9 is unchanged and the exit code is 0

#### Scenario: Python type comment counts as code
- **WHEN** `--keep src/a.py:4` names a line whose only spelling of the old name is in `# type: Old`, without `--docs`
- **THEN** the check passes and the run goes on to `references`

#### Scenario: Missing classification site
- **WHEN** a member rename passes `--with src/gone.py:3` and `--without src/a.py:400`
- **THEN** stderr lists `refactor.site-missing` for both, no `[references]` line is printed and the exit code is 2

#### Scenario: Unresolved entries listed together
- **WHEN** map entries 2 and 4 name symbols their files do not declare
- **THEN** stderr lists `refactor.symbol-unresolved` for entry 2 and then for entry 4, each inside
  `refactor.entry-refusal` naming its entry and locator, and the exit code is 2

#### Scenario: Taken module name before any search
- **WHEN** a map renames function `f` and module `pkg/a.py` to `b`, where `pkg/b.py` exists; or function `f` and module
  `src/a.ts` to `b`, where `src/b.ts` exists
- **THEN** stderr is `[resolve]`, `[checks]` and `refactor.name-conflict` naming `pkg/b.py` or `src/b.ts` line 1, no
  `[references]` line is printed, the exit code is 1 and nothing changes

#### Scenario: Invalid module new name before any search
- **WHEN** `rename --file pkg/a.py --new-name a/b` or `rename --file src/a.ts --new-name a/b` runs
- **THEN** stderr is `[resolve]`, `[checks]` and `refactor.cannot-rename`, no `[references]` line is printed, the exit
  code is 1 and nothing changes

#### Scenario: Unresolved entry and bad keep
- **WHEN** entry 1 does not resolve and `--keep src/gone.py` is passed
- **THEN** stderr lists the entry's finding and then `refactor.site-missing`, and the exit code is 2

#### Scenario: Keep matched by an escaped spelling
- **WHEN** `--keep src/a.py:7` names a line whose only spelling of the old name is an escaped string literal
- **THEN** the check passes and the run goes on to `references`

#### Scenario: Keep on a retarget's import line
- **WHEN** a TypeScript retarget passes `--keep` on an import of the target that the retarget removes as a duplicate
- **THEN** the check passes and the import line is unchanged

#### Scenario: Keep of a prose file needs --docs
- **WHEN** `--keep README.md:3` names a line of a prose file that mentions the old name
- **THEN** the check passes with `--docs`, and without it stderr is `refactor.keep-unmatched` naming it

#### Scenario: Walker gaps listed before any search
- **WHEN** rope's walker cannot cover `pkg/a.py` at line 3 nor `pkg/b.py` at line 8, and both spell the name a
  `move-symbol` moves
- **THEN** stderr lists `refactor.rope-walk` for both files in path order, no `[references]` line is printed, the
  exit code is 1 and no file changes

#### Scenario: Checker that cannot run
- **WHEN** `commands.typecheck.python` names a command that exits 2 with a message on stderr, and the baseline file
  exists
- **THEN** stderr ends with `refactor.baseline-failed` and its cause, no `[references]` line is printed and the exit
  code is 1

#### Scenario: Unreadable config
- **WHEN** a rename runs where the language's baseline file exists and `living-architecture.yaml` is not valid YAML
- **THEN** stderr ends with the config error, no `[references]` line is printed, the exit code is 2 and no file
  changes

#### Scenario: Entries that cannot be located
- **WHEN** a three-entry map's entry 2 is `{file: pkg/c.py, line: 2, col: 11}` on a keyword and its entry 3 is
  `{file: pkg/c.py, line: 2, col: 5}` on whitespace
- **THEN** stderr is `[resolve]`, `[checks]`, then `refactor.entry-refusal` for `entry 2 (pkg/c.py:2:11)` and for
  `entry 3 (pkg/c.py:2:5)`, each holding `refactor.cannot-rename`, and the exit code is 1

#### Scenario: Collision in the declaring scope found before any search
- **WHEN** a map renames member `Q.measures` to `metrics` where `Q` declares `metrics`, parameter `f(x)` to `y` where
  `f` has a parameter `y`, a local `a` of `g` to `b` where `g` binds `b`, and top-level `one` to `two` where the
  module binds `two`, and no entry renames any of the existing names
- **THEN** stderr is `[resolve]`, `[checks]` and four `refactor.name-conflict` findings, one per entry in entry order,
  each inside `refactor.entry-refusal` and naming the existing declaration's line; no `[references]` line is printed
  and the exit code is 1

#### Scenario: Python member declared through self
- **WHEN** a Python map renames `C.old` to `fresh` where a method of `C` assigns `self.fresh`
- **THEN** the map is refused in `checks` with `refactor.name-conflict` naming the line of that assignment

#### Scenario: Names the language lets share a scope
- **WHEN** a TypeScript map renames interface `A` to `B` where the module declares a function `B` and no type `B`;
  or renames instance method `C.a` to `b` where `C` declares a static `b`; or renames a `let x` of one block to `y`
  where a sibling block declares `y`
- **THEN** the checks pass and each rename applies

#### Scenario: Python scopes that do not collide
- **WHEN** a Python map renames a function's local `a` to `b` where only a nested function, a comprehension in it or
  a class nested in it binds `b` and none of them reads `a`
- **THEN** the checks pass and the rename applies

#### Scenario: Kept declaration left to the conflicts phase
- **WHEN** a map renames `Q.measures` to `metrics` where `Q` declares `metrics`, with `--keep` on the line declaring
  `Q.measures`
- **THEN** stderr holds a `[references]` line: the `checks` phase refuses nothing for that pair

#### Scenario: Sites from outside the project
- **WHEN** `dr-refactor --project proj rename-map ...` runs from the directory holding `proj` with
  `--keep pkg/a.py:7`, `--with pkg/b.py:5` or `--without pkg/b.py:5`, each a path under `proj`
- **THEN** each site is found; the same run with `--keep proj/pkg/a.py:7` prints `refactor.site-missing`, exit 2

### Requirement: Every refusal of a run is reported in one report
A run SHALL refuse once, with every refusal it found: those of `resolve` and `checks` as one report before any
reference search, else every refusal found while computing the entries. A walker gap the checks did not predict and
an unresolved base SHALL be recorded and the run SHALL go on. Once every entry's edits are final, site resolution
SHALL decide every `--keep`, `--with` and `--without` site exactly (see the `--keep` and stand-in requirements); it
SHALL be skipped after a `--fail-fast` stop and, in the Python twin, when an entry failed while computing. When it
finds a refusing site finding, the run SHALL stop there, before `conflicts`, and report. Otherwise, after
`conflicts`, every site two entries rewrite differently SHALL be reported, or, when there is none, each entry's
first name conflict (each distinct finding once).

Each refusal SHALL be printed once. A group's refusals (its entries' failures while computing, retarget refusals,
blind spots, stand-ins) SHALL be printed under its `[rules]` line only. The final report SHALL hold only what no
`[rules]` line printed: the failures of entries whose group printed no line (a module entry's, or an entry's after
a `--fail-fast` stop before `rules`) by entry index; name conflicts by entry index; map conflicts in path, line
and column order; then the site findings
(`refactor.not-stand-in` for the `--with` and then the `--without` sites, then `refactor.computed-stand-in`, then
the keep findings, each in command-line order); then the `refactor.blindspots` line when blind spots refuse. With
nothing to hold, the final report SHALL print nothing. The run's exit code SHALL be the highest of all its
refusals', wherever they were printed, 2 for an invalid or duplicate map entry (`refactor.map-invalid`,
`refactor.map-duplicate`), a locator or a site finding, and 1 otherwise, `refactor.map-conflict` included. A file
that changed while the run read it, a write that failed, a checker that failed while computing, and a map document
that cannot be read SHALL still stop the run at once.

A refusal of one entry SHALL be printed as `refactor.entry-refusal`: the entry's label (`refactor.progress-entry`, or
`refactor.progress-entries` with every map index merged into it), its locator as the map writes it (`FILE:LINE:COL`,
`FILE:LINE`, `FILE SYMBOL`, `FILE offset N`, or a module entry's path, FILE relative to `--project`), then the
finding. This SHALL hold for every resolution failure, every failure of an entry while computing, and every
`refactor.name-conflict` of `rename`, `retarget` and `rename-map`, whichever check finds it. A name conflict SHALL
belong to the entry whose new name it names; when the renamed declarations of two or more entries meet, to the
latest of them, naming the earliest one's first declaration. Findings that name their entries themselves
(`refactor.map-invalid`, `refactor.map-duplicate`, `refactor.map-conflict`, `refactor.map-module-unsupported`),
a group's other refusals under its `[rules]` line, and findings of the run as a whole (sites, keeps, `--stub`, the
checker, the config, a write) SHALL be printed as they are. `move-symbol` and `move-module` have no entries and
SHALL print their findings as they are.

#### Scenario: Retarget refusal and blind spot together
- **WHEN** a map's retarget entry meets an overriding member and its rename entry meets an untyped receiver
- **THEN** each is printed once, under its group's `[rules]` line, the final report is the `refactor.blindspots`
  line, and the exit code is 1

#### Scenario: Late unmatched keep with other refusals
- **WHEN** `--keep src/a.py:5` names a code line spelling the old name where no edit lands, and an entry meets an
  untyped receiver
- **THEN** stderr holds the blind spot once, under its group's `[rules]` line, no `[conflicts]` line, and a final
  report of the keep finding naming `src/a.py:5` and then the `refactor.blindspots` line; the exit code is 2

#### Scenario: Unneeded keep and unmatched line keep together
- **WHEN** a rename passes an unneeded `--keep src/compat.py` and a line keep `--keep src/a.py:5` that matches nothing
- **THEN** stderr holds `refactor.keep-unneeded` naming `src/compat.py`, then the final report with the line keep's
  finding, no `[conflicts]` line, and the exit code is 2

#### Scenario: Unneeded keep with a blind spot
- **WHEN** a rename passes an unneeded `--keep src/compat.py` and an entry meets an untyped receiver
- **THEN** stderr holds the blind spot under its group's `[rules]` line, then `refactor.keep-unneeded`, then
  `[conflicts]`, then the `refactor.blindspots` line, and the exit code is 1

#### Scenario: Two map conflicts
- **WHEN** two pairs of entries each rewrite one site differently
- **THEN** stderr lists `refactor.map-conflict` for both sites in path order and the exit code is 1

#### Scenario: Stand-in printed once
- **WHEN** a one-entry map renames `A.m` and an unrelated class `B` declares `m`
- **THEN** stderr holds the `refactor.stand-in` line once, under `[rules 1/1]`, then `[conflicts]` and nothing
  after it, and the exit code is 1

#### Scenario: Literal-unresolved printed once
- **WHEN** a `Literal` member rename meets a site the checker needs the old value at
- **THEN** stderr holds that `refactor.literal-unresolved` line once and the exit code is 1

#### Scenario: Entry failing while it is computed
- **WHEN** entries 1 and 2 of a map share an old name and entry 2's new name is a keyword
- **THEN** the group's `[rules]` line is followed by `refactor.entry-refusal` for entry 2 holding
  `refactor.cannot-rename`, printed once, and the exit code is 1

#### Scenario: Name conflict names its entry
- **WHEN** entry 2 of a map renames a module-level `old` to `next` and a function binds a local `next` and reads `old`
- **THEN** stderr ends with `refactor.entry-refusal` for entry 2 and its locator, holding the `refactor.name-conflict`
  finding

#### Scenario: Single rename names entry 1
- **WHEN** `rename --file F --line 2 --col 11 --new-name n` points at a keyword
- **THEN** stderr ends with `refactor.entry-refusal` for `entry 1 (F:2:11)` holding `refactor.cannot-rename`, as the
  one-entry map prints it

### Requirement: --fail-fast stops at the first refusal
`dr-refactor rename`, `retarget` and `rename-map` SHALL accept `--fail-fast`. With it, the run SHALL stop at the first
refusal found after `checks`: the entry or group in progress SHALL finish its phase and print its line, no later one
SHALL start that phase and no later phase SHALL run. The final report SHALL list what was found and not yet printed, without site
resolution (no exact site finding and no `refactor.keep-unneeded`). Without it, every entry SHALL be computed and
every refusal reported, up to a stop at site resolution.

#### Scenario: Stop after the first refused group
- **WHEN** a three-entry map with distinct old names runs with `--fail-fast` and its first entry meets an untyped
  receiver
- **THEN** stderr holds one `[rules 1/3]` refused line followed by that blind spot, printed once, no `[rules 2/3]`
  line, a final report of the `refactor.blindspots` line, and the exit code is 1

#### Scenario: Default computes every entry
- **WHEN** the same map runs without `--fail-fast` and its first and third entries each meet an untyped receiver
- **THEN** stderr holds three `[rules]` result lines, each blind spot once under its own, and a final report of the
  `refactor.blindspots` line

#### Scenario: Stop on a stand-in
- **WHEN** a two-entry map with distinct old names runs with `--fail-fast` and its first entry meets an unclassified
  stand-in
- **THEN** stderr holds the `[rules 1/2]` refused line and the `refactor.stand-in` line once, nothing after it, and
  the exit code is 1

### Requirement: A failed checker's cause is printed
When the Python language server or the configured Python checker fails, its finding (`refactor.pyright-failed` or
`refactor.baseline-failed`) SHALL be followed by its cause: `refactor.checker-exit` with its exit code and then its
stderr lines, each indented by two spaces; `refactor.checker-not-started` with the error when it could not start; or
`refactor.checker-error` with its error answer, then any stderr captured. A baseline file that cannot be read SHALL
print `refactor.baseline-failed` with no cause.

#### Scenario: Language server that cannot start
- **WHEN** the language server's command does not exist
- **THEN** stderr ends with `refactor.pyright-failed` and `refactor.checker-not-started`, and the exit code is 1

#### Scenario: Checker failing during alignment
- **WHEN** the configured checker passes the probe and exits 2 with a message while realigning the baseline
- **THEN** stderr ends with `refactor.baseline-failed`, `refactor.checker-exit` naming exit code 2 and the message
  indented by two spaces, the exit code is 1 and nothing is written

### Requirement: Python refactors resolve every occurrence from one occurrence index
A Python `dr-refactor` `rename`, `rename-map` or `retarget` of symbols other than modules, and Python
`dr-compliance --attr`, SHALL resolve every occurrence of the old names from one occurrence index of the run: for each
occurrence of an old name in the candidate files (the project's Python sources whose text holds an old name, or a
string constant equal to one under any escaped spelling), its kind (name, member access, keyword argument, dict-literal
key, string-member name, dotted patch target, `Literal`-typed string, forward-reference string, `__all__` entry, import
alias or re-export), the declarations the checker resolves it to (aliases followed, every overload) with every
import-alias or re-export binding it passes through on the way, each with the class declaring it and that class's MRO, and for an access or a string-member object whether the checker types its
receiver. la's language server SHALL export the index in a number of requests that does not depend on the number of
entries or occurrences, and SHALL answer no find-all-references request and no per-occurrence position query for it.

rope SHALL play no part in a Python `rename`, `rename-map` or `retarget`, of a symbol or of a module. A name, import or
alias occurrence of an old name that the checker resolves to no declaration SHALL be resolved by Python's scoping
rules and the project's own modules, without importing or running them: one that resolves to a declaration the rename
renames SHALL be renamed; one that resolves to another declaration SHALL be left; one that resolves to nothing (a name
bound nowhere, or bound by an import of a module neither the checker nor the project's source folders hold) SHALL be
left and listed with the `refactor.unresolved-name` finding on stderr, which does not change the exit code. These lines
SHALL be printed with the leftovers, sorted by path, line and column, and a `--keep` covering a line SHALL drop its
line.

The export SHALL run under the same verification as la's pyright#11919 patch: a basedpyright version it is not
verified for, or a hook that does not match the bundle exactly, SHALL make `dr-refactor` print the
`refactor.pyright-failed` finding on stderr, write nothing and exit 1, and `dr-compliance --attr` print
`compliance.pyright-failed` and exit 2. An exported span that does not slice to the old name's spelling in the file as
read SHALL be refused the same way. The language server SHALL start only when the run needs it, and at most once per
run; a run whose every entry is a module rename, `move-symbol` and `move-module` SHALL NOT start it.

#### Scenario: Export cost does not grow with entries
- **WHEN** a `rename-map` of one entry and a `rename-map` of ten entries run over the same project
- **THEN** both send the same number of export requests, neither sends a references, hover or definition request per
  occurrence, and each prints the same diff as the equivalent single renames merged

#### Scenario: Every member occurrence kind
- **WHEN** field `Model.columns` of a Pydantic model is renamed in a project holding a read `m.columns` with
  `m: Model`, a keyword `Model(columns=[])`, a dict key `Model.model_validate({"columns": []})`,
  `getattr(m, "columns")`, `patch.object(Model, "columns")` and `patch("pkg.mod.Model.columns")`
- **THEN** each of them is renamed, and the output is byte-identical to the output before this change

#### Scenario: Every name occurrence kind
- **WHEN** module-level class `Rec` of `pkg/mod.py` is renamed in a project holding a forward reference `x: "Rec"`, an
  `__all__` entry `"Rec"`, `from pkg.mod import Rec as R`, and a package `__init__.py` re-exporting it with
  `from pkg.mod import Rec` that another module imports from the package
- **THEN** every `Rec` among them is renamed while the alias `R` and its uses stay, and the output is byte-identical
  to the output before this change

#### Scenario: Entry located on an import alias
- **WHEN** `pkg/compat.py`'s `from pkg.core import Model as AcmeModel` is retargeted to `Model`, `pkg/use.py` imports
  `AcmeModel` from `pkg.compat`, and `pkg/other.py` declares its own `from pkg.core import Model as AcmeModel`
- **THEN** the import and the use in `pkg/use.py` are retargeted, `pkg/other.py` is unchanged, and
  `refactor-retarget-reexport-form`'s output is byte-identical to the output before this change

#### Scenario: Overloads, super() and Protocol members
- **WHEN** an overloaded method, a method called through `super().name(...)` in an override, and a member of a
  `Protocol` that a class implements by inheritance are each renamed
- **THEN** every overload signature, the `super()` call and the protocol's and implementer's declarations are renamed

#### Scenario: Import the checker cannot resolve
- **WHEN** `pkg/a.py`'s `foo` is renamed and `scripts/use.py` holds `from pkg.a import foo` and `foo()`, while the
  project's checker configuration does not put the project root on its search path, so basedpyright resolves neither
- **THEN** both occurrences in `scripts/use.py` are renamed, as Python's import rules over the project's source
  folders resolve them

#### Scenario: Name nothing resolves
- **WHEN** `lib/a.py`'s `foo` is renamed and `scripts/use.py` holds `from acme.a import foo` and `foo()`, where no
  source folder of the project holds `acme` and the checker resolves neither
- **THEN** both lines of `scripts/use.py` are unchanged, stderr lists `refactor.unresolved-name` for line 1 and for
  the line of the call after the diff, and the exit code is 0

#### Scenario: Unresolved name kept
- **WHEN** the same rename passes `--keep scripts/use.py`
- **THEN** no `refactor.unresolved-name` line is printed for `scripts/use.py`

#### Scenario: A resolved local is not listed
- **WHEN** `pkg/a.py`'s module-level `foo` is renamed and another function binds its own local `foo` and reads it
- **THEN** the local and its read are unchanged and no `refactor.unresolved-name` line names them

#### Scenario: Unverified checker
- **WHEN** a rename runs with a bundled basedpyright version the export is not verified for
- **THEN** stderr is the `refactor.pyright-failed` finding followed by its cause, the exit code is 1 and every file of
  the project is unchanged

#### Scenario: Positions after astral characters and CRLF in every kind
- **WHEN** each occurrence kind of "Every member occurrence kind" and "Every name occurrence kind" sits in a module with CRLF line endings, a lone `\r`, and
  astral characters before it on its line
- **THEN** exactly the old name is replaced at each, and the line endings are kept

#### Scenario: No server for a module move
- **WHEN** `move-module` or a module rename runs
- **THEN** no language server starts

### Requirement: The Python occurrence index is cached between runs
`dr-refactor` and `dr-compliance --attr` SHALL reuse an earlier run's occurrence index exactly when nothing that can
change it has changed: the content of every project source file and the set of those files, the checker's effective
configuration, the interpreter and its search paths, the installed packages and stubs, the basedpyright and export
versions, and the request (the old names, the candidate files and every queried position). Otherwise they SHALL
export the index anew. The cache SHALL hold one entry per project root, in the directory named by `LA_CACHE_DIR` when
it is set, else in the user's cache directory, and never in the project. A missing, unreadable or corrupt cache SHALL
count as absent. Output SHALL be identical with and without a cache entry.

#### Scenario: Re-run after fixing flags
- **WHEN** a `rename-map` dry run refuses on stand-ins and is re-run with `--without` for each, no file having changed
- **THEN** the second run exports nothing and prints the same output as a run without a cache

#### Scenario: A source edit invalidates
- **WHEN** a project source file changes, a file is added that shadows an import, or a file is deleted between two
  runs
- **THEN** the second run exports the index anew

#### Scenario: Environment change invalidates
- **WHEN** the checker configuration, the interpreter or an installed package changes between two runs
- **THEN** the second run exports the index anew

#### Scenario: Corrupt cache
- **WHEN** the cache entry for the project is truncated or not valid
- **THEN** the run exports the index anew and its output equals a run without a cache

#### Scenario: Nothing written in the project
- **WHEN** a rename runs with and without `--apply`
- **THEN** no cache file exists under the project

### Requirement: Python --unsure include renames unresolved receivers
With `--unsure include`, a Python rename SHALL also rename every access `x.OLD` whose receiver the checker types as
`Unknown`, `Any` or a union holding either, and SHALL print the `refactor.unsure-warning` finding on stdout before the
diff. Blind spots SHALL be reported, refused and let through by `--allow-blindspots` as without it. With the default
`--unsure skip` no such access SHALL be renamed.

#### Scenario: Untyped receiver renamed on request
- **WHEN** method `A.run` is renamed with `--unsure include --allow-blindspots` and a module holds `def f(o): o.run()`
- **THEN** `o.run()` becomes `o.<new>()`, stdout starts with the `refactor.unsure-warning` line, and the blind spot is
  listed on stderr

#### Scenario: Skipped by default
- **WHEN** the same rename runs with `--allow-blindspots` only
- **THEN** `o.run()` is unchanged and the blind spot is listed on stderr

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

### Requirement: TypeScript module renames
`rename --file F --new-name N` with no locator, and a `rename-map` entry `{module: F, new_name: N}`, SHALL rename the
TypeScript module `F`, a source file of any extension the registry gives TypeScript, a declaration file included. `F`
SHALL move to `N` followed by its own extension (a declaration file's whole declaration extension) in its own
directory. A directory and an `index` file SHALL get no special meaning: `F` is always the one file. In every project
the refactor computes a rename in, every specifier resolving to `F` (import and export declarations, `import()` calls
and types, `import x = require()`, `require()` in a JavaScript source, module declarations) SHALL be rewritten to name
the new path, keeping its form, together with every edit the language service makes for the move in other files; mock
module paths SHALL follow as "TypeScript module moves rewrite mock module paths" defines. Local names an import of `F`
binds SHALL be unchanged.

The module's old name SHALL be `F`'s file name without that extension. Its header SHALL be `refactor.rename-header`,
its move SHALL be printed as one `rename from`/`rename to` pair, and an edit in `F` SHALL be printed at `F`'s old path
and, with `--apply`, written before the move. A new name equal to the old name SHALL change nothing.

A new name that is empty, `.` or `..`, holds `/`, `\` or NUL, or ends in a TypeScript source or declaration extension
SHALL be refused with `refactor.cannot-rename` as a resolution failure. A module rename SHALL be refused with
`refactor.name-conflict` in the `checks` phase, before any reference search, exit 1, writing nothing, when `F`'s
directory already holds, in the code before the refactor, a file other than `F` named `N` followed by any TypeScript source or
declaration extension (naming it at line 1), or a directory named `N` (naming its `index` source file at line 1, else
its first file by path); a file of another extension SHALL NOT count. In a map, module entries whose new names are one
name in one directory SHALL be refused with `refactor.name-conflict` naming the earlier entry's file at line 1, in the
`conflicts` phase.

`--stub` SHALL be refused in a TypeScript run with `refactor.stub-not-module` in the `checks` phase, exit 2. A file in no
project SHALL be refused with the outside-project finding. The type-check baseline SHALL be realigned through the move.

#### Scenario: Rename without a locator
- **WHEN** `--apply rename --file src/a.ts --new-name b` runs, `src/use.ts` holds `import { f } from './a.js'` and
  `test/t.ts` holds `export * from '../src/a'`
- **THEN** `src/a.ts` is at `src/b.ts`, the importers read `./b.js` and `../src/b`, stdout holds the rename header, the
  `rename from src/a.ts`/`rename to src/b.ts` pair and both diffs, and the exit code is 0

#### Scenario: Extension kept
- **WHEN** `src/x.d.ts` is renamed to `y` and `src/a.test.ts` to `c`
- **THEN** they move to `src/y.d.ts` and `src/c.ts`, and the second header names the old name `a.test`

#### Scenario: An index file is a file
- **WHEN** `src/lib/index.ts` is renamed to `main` and `src/use.ts` imports `./lib/index.js`
- **THEN** the file moves to `src/lib/main.ts`, the directory stays, and the import reads `./lib/main.js`

#### Scenario: Invalid new name
- **WHEN** a module rename's new name is `b.ts`, `a/b` or `..`
- **THEN** stderr is `[resolve]`, `[checks]` and `refactor.cannot-rename`, the exit code is 1 and nothing changes

#### Scenario: Name taken by a sibling
- **WHEN** `src/a.ts` is renamed to `b` in one project holding `src/b.tsx`, in one holding `src/b/index.ts`, and in one
  holding only `src/b/util.ts` and `src/b/zed.ts` under `src/b/`
- **THEN** each is refused after `[resolve]` and `[checks]` with `refactor.name-conflict` naming `src/b.tsx` line 1,
  `src/b/index.ts` line 1 and `src/b/util.ts` line 1, and nothing changes

#### Scenario: A sibling of another language
- **WHEN** `src/a.ts` is renamed to `b` and `src/b.json` and `src/b.css` exist
- **THEN** the rename applies

#### Scenario: Renamed to its own name
- **WHEN** `src/a.ts` is renamed to `a`
- **THEN** no file changes and the exit code is 0

#### Scenario: Local import names stay
- **WHEN** `src/a.ts` is renamed to `b` and `src/use.ts` holds `import * as a from './a.js'` and `a.f()`
- **THEN** the import reads `import * as a from './b.js'` and `a.f()` is unchanged

#### Scenario: Module renamed across project references
- **WHEN** a solution tsconfig references `core` and `app`, and `app` imports and re-exports `core`'s `src/a.ts`, which
  is renamed to `b`
- **THEN** each specifier in `app` is rewritten once, the output equals that of the one-entry map, and the exit code is 0

#### Scenario: Stub refused
- **WHEN** a TypeScript module rename runs with `--stub 2.0`
- **THEN** stderr is `[resolve]`, `[checks]` and `refactor.stub-not-module`, the exit code is 2 and nothing changes

#### Scenario: New names meeting in one directory
- **WHEN** a map renames `src/a.ts` to `c` and `src/b.tsx` to `c`, where no `c` exists
- **THEN** stderr's final report is `refactor.name-conflict` naming `src/a.ts` line 1 after `[conflicts]`, the exit code
  is 1 and nothing changes

### Requirement: TypeScript module moves rewrite mock module paths
A TypeScript module rename and `move-module` SHALL rewrite the module path of every mock call naming a moved file: a
call, on a receiver bound to a test framework, of a method the shared language facts list as taking a module path,
whose module argument is a string literal that resolves, by the program's module resolution from its file, to a moved
file. The path SHALL be rewritten as the language service rewrites an import of the same specifier in that file: a
relative specifier stays relative and keeps its extension style, and a `paths`-mapped one keeps its mapping. A receiver
SHALL be bound to a framework when it is a named import, aliased or not, of the framework's receiver from the
framework's module, or the unshadowed global of that name; any other receiver, such as a local of that name or a
namespace import's member, SHALL be left.

#### Scenario: Vitest mock paths
- **WHEN** `src/api.ts` is renamed to `client` and a test holds `vi.mock('../src/api')`, `vi.doMock('../src/api.js', f)`,
  `vi.importActual('../src/api')` and `vi.mock(import('../src/api'), f)`
- **THEN** each reads `../src/client` or `../src/client.js` in its own extension style

#### Scenario: Jest typed factory agrees
- **WHEN** a test holds `j.mock<typeof import('../src/api')>('../src/api', f)` with `j` imported as `jest` from
  `@jest/globals`, and `src/api.ts` is renamed
- **THEN** the type argument and the string both name the new module

#### Scenario: Mapped mock path
- **WHEN** the project maps `@/*` to `src/*`, a test holds `vi.mock('@/api')` and `import { get } from '@/api'`, and
  `src/api.ts` is renamed to `client`
- **THEN** both read `@/client`

#### Scenario: Receivers left
- **WHEN** a test binds a local `const vi = { mock: (p: string) => p }` and calls `vi.mock('../src/api')`, and another
  holds `import * as vitest from 'vitest'` and `vitest.vi.mock('../src/api')`
- **THEN** neither string changes

#### Scenario: Mock path of a moved module
- **WHEN** `move-module --module src/api.ts --dest src/lib` runs and a test holds `vi.mock('../src/api.js')`
- **THEN** the string reads `../src/lib/api.js`

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
