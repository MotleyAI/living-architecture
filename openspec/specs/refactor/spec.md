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
only another language lists SHALL not apply to a file. Python's checks and their output SHALL be unchanged.

#### Scenario: Python default unchanged
- **WHEN** `dr-compliance pkg` runs without `--select` in a Python repo
- **THEN** stdout equals today's golden

#### Scenario: Language-specific id
- **WHEN** `dr-compliance --select explicit-any pkg/a.py` runs
- **THEN** nothing is reported and the exit code is 0

### Requirement: TypeScript compliance checks
The TypeScript checks SHALL be: `tsconfig`, one finding per governing tsconfig and per flag whose effective
value after `extends` resolution is not true, among `strict`, `noImplicitAny` and `noImplicitOverride`;
`explicit-any`, every `any` type in the file; `untyped-def`, every parameter, binding element or rest parameter
whose type is implicitly `any` as the type checker determines it with `noImplicitAny` in force (return types
are not required); and `mock`, the TypeScript mock-lint rules. `--attr NAME` SHALL report `x.NAME` accesses
whose receiver's type is `any`. Findings SHALL be sorted per file; a file that does not parse SHALL produce the
parse-error finding.

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
