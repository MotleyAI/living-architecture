# affected-tests Specification

## Purpose
`la-affected-tests` prints the test files a branch's change can affect — the tests it added or changed and every
test whose imports reach a changed file — so a local run can skip the tests the change cannot break.

## Requirements

### Requirement: The command prints the affected test files of a change against a base branch
`la-affected-tests --base BRANCH` SHALL compare the working tree with `origin/<BRANCH>` (after a best-effort
`git fetch origin <BRANCH>`, exactly as `la-check-conventions --base`), and print on stdout every selected test
file as a path relative to the repository's top-level directory, in POSIX form, one per line, unique, sorted by
Unicode code point. It SHALL never run a test. It SHALL exit 0 when it completes, including when nothing is
selected (empty stdout). Its output SHALL NOT depend on the working directory inside the repository. `--base` is
required for a public invocation; missing it is a usage error (exit 2).

#### Scenario: Nothing changed
- **WHEN** `la-affected-tests --base main` runs on a branch identical to `origin/main` with a clean working tree
- **THEN** it exits 0 with empty stdout

#### Scenario: Run from a subdirectory
- **WHEN** it runs from a nested directory of the repository
- **THEN** stdout equals the run from the repository root, paths relative to the top level

#### Scenario: Missing base option
- **WHEN** `la-affected-tests` runs without `--base`
- **THEN** it exits 2 with a usage error

#### Scenario: Code-point order
- **WHEN** the selection contains paths with non-ASCII and mixed-case names
- **THEN** they are printed in Unicode code-point order

### Requirement: The changed set covers committed, working-tree and untracked changes, deletions included
The changed set SHALL be the union of the files changed between the merge base of `origin/<BRANCH>` and `HEAD`,
the files changed between `HEAD` and the working tree (staged or not), and the untracked files that are not
ignored. Deleted files SHALL be in the changed set. A rename SHALL count as the deletion of the old path and the
addition of the new one. Git paths SHALL be read NUL-delimited, independent of `core.quotePath`.

#### Scenario: Staged-only and unstaged-only edits
- **WHEN** one test file is changed and staged and another is changed but not staged, with no commit
- **THEN** both are printed

#### Scenario: Untracked new test
- **WHEN** a new test file exists in the working tree and is not tracked
- **THEN** it is printed

#### Scenario: Ignored file
- **WHEN** a new test file matches `.gitignore`
- **THEN** it is not printed

#### Scenario: Rename
- **WHEN** a source module is renamed and a test imports its old dotted name or path
- **THEN** that test is printed

#### Scenario: Unusual but representable names
- **WHEN** a changed test path contains spaces or non-ASCII characters, with `core.quotePath` true
- **THEN** it is printed verbatim

### Requirement: Changed test files are selected
Every file in the changed set that still exists, has a source extension of a language in the shared languages
registry, and matches that language's `test_globs` SHALL be printed. A deleted test file SHALL NOT be printed.

#### Scenario: Changed test only
- **WHEN** only `tests/test_a.py` changed
- **THEN** stdout is `tests/test_a.py`

#### Scenario: Deleted test
- **WHEN** a test file was deleted
- **THEN** it is not printed

#### Scenario: Non-source change only
- **WHEN** only a YAML file changed and no file imports it
- **THEN** it exits 0 with empty stdout

### Requirement: Tests whose imports reach a changed file are selected
For each computed language — one with a file in the changed set, or one whose `imports_non_source` fact in the
shared languages registry is true when a changed path has no source extension of any language and the repository
has files of that language — the command SHALL build a graph over the repository's
files of that language (tracked plus untracked-not-ignored) and that language's deleted changed paths, with an
edge from each file to every file one of its imports resolves to. Every import SHALL count, including imports
only for type checking (Python imports under `if TYPE_CHECKING:`; TypeScript `import type`, `export type`, type-only
specifiers and `import('x')` types). It SHALL walk the reversed edges transitively from every changed or deleted
file of the language (for a language with `imports_non_source`, also from every changed path with no source
extension), whether or not that file is a test file, and print every reached file that matches the
language's `test_globs`. Cycles SHALL terminate. No architecture index or configuration SHALL be needed.

#### Scenario: Transitive reach
- **WHEN** `src/pkg/b.py` changed, `src/pkg/a.py` imports `pkg.b`, `tests/test_a.py` imports `pkg.a`, and `tests/test_c.py` imports neither
- **THEN** `tests/test_a.py` is printed and `tests/test_c.py` is not

#### Scenario: Changed test helper
- **WHEN** `tests/helpers.py` changed and `tests/test_x.py` imports `helpers`
- **THEN** both `tests/helpers.py` and `tests/test_x.py` are printed

#### Scenario: Type-only edge
- **WHEN** a test reaches a changed module only through an import under `if TYPE_CHECKING:` (Python) or an `import type` (TypeScript)
- **THEN** the test is printed

#### Scenario: Deleted module still imported
- **WHEN** a source module was deleted and a test still imports it
- **THEN** the test is printed

#### Scenario: Import cycle
- **WHEN** two modules import each other and one of them changed
- **THEN** the command terminates and prints the tests reaching either module

#### Scenario: No architecture index
- **WHEN** the repository has no `architecture/` directory
- **THEN** the selection is the same as with one

### Requirement: Python imports resolve to files by dotted suffix
A Python file's imports SHALL be read both from its syntax tree and from a lexical scan of its text, and its edges
SHALL be the union of both; a file whose syntax tree cannot be built contributes its lexical edges. An absolute
import of `a.b.c` SHALL resolve to every graph file whose path ends, at a directory boundary, in `a/b/c.py` or
`a/b/c/__init__.py`, and also to each `__init__.py` of the packages along each match (`<dir>/a/__init__.py`,
`<dir>/a/b/__init__.py`). `from a.b import c` SHALL also resolve `a.b.c`. A relative import of level N SHALL resolve
against the importer's directory with N-1 parent steps, probing the imported module and each imported name as a
module (`<dir>/x.py`, `<dir>/x/__init__.py`) and the package itself (`<dir>/__init__.py`). Every Python file SHALL
also depend on the `__init__.py` files of the directories containing it, up to the first directory without one.

#### Scenario: Same module under several roots
- **WHEN** `a/b.py` exists under two directories and a test imports `a.b`
- **THEN** a change to either file selects the test

#### Scenario: Parent package initializer
- **WHEN** `src/pkg/__init__.py` changed and a test imports `pkg.sub.mod`
- **THEN** the test is printed

#### Scenario: Relative import from a package initializer
- **WHEN** `pkg/sub/__init__.py` contains `from . import x` and `from .. import y`, `pkg/sub/x.py` and `pkg/y.py` changed, and a test imports `pkg.sub`
- **THEN** the test is printed for each change

#### Scenario: File the tool's parser rejects
- **WHEN** a Python test file contains syntax the twin's interpreter cannot parse and imports a changed module
- **THEN** the test is printed

### Requirement: TypeScript imports resolve under each file's nearest tsconfig
A TypeScript or JavaScript file's module specifiers (static and dynamic imports and exports, `import x =
require()`, literal `require()`, type-only forms, `import('x')` types and `/// <reference path>`) SHALL resolve with
the TypeScript module resolver under the nearest `tsconfig.json` from the file's directory up to the repository
root (else default options), following its project references. Deleted changed paths SHALL resolve as if present.
A resolved file SHALL be an edge target when its path, or for a path through `node_modules` its real path, is
inside the repository and outside `node_modules`, whatever its extension. A relative specifier the resolver cannot
resolve SHALL resolve to every graph file at that path with one source extension stripped and any source extension
added, or at `<path>/index.<source extension>`.

#### Scenario: Path alias
- **WHEN** a test imports `@lib/util` mapped by its tsconfig `paths` to a changed `src/lib/util.ts`
- **THEN** the test is printed

#### Scenario: JSON module
- **WHEN** `src/data.json` changed and a test imports it
- **THEN** the test is printed

#### Scenario: Deleted directory index
- **WHEN** `src/feature/index.ts` was deleted and a test imports `../src/feature`
- **THEN** the test is printed

#### Scenario: Workspace package
- **WHEN** a test imports a workspace package symlinked under `node_modules` whose source in the repository changed
- **THEN** the test is printed

### Requirement: Both languages are selected through either twin
The invoking twin SHALL compute the changed set once and its own language's selection natively. For the other
language, when it is computed, it SHALL obtain that language's selection from the other twin
through an internal request carrying the changed paths, and print the union. A language that is not computed
SHALL NOT have its twin probed. Stdout SHALL be byte-identical whichever twin
is invoked. When the other twin is needed and unreachable or its request fails, the command SHALL print nothing
on stdout and exit 2 with the twin's hint.

#### Scenario: Two-language change
- **WHEN** a change touches a Python module and a TypeScript module, each reached by a test
- **THEN** both tests are printed, identically through either twin

#### Scenario: Own-language change needs no twin
- **WHEN** only Python files changed and the npm twin is unreachable, invoked through the PyPI twin
- **THEN** it completes natively

#### Scenario: Other twin unreachable
- **WHEN** a TypeScript file changed and the npm twin is unreachable, invoked through the PyPI twin
- **THEN** it exits 2 with the install hint and empty stdout

### Requirement: Setup and git failures exit 2
The command SHALL exit 2 with a shared message on stderr and nothing on stdout when it runs outside a git
repository, when `origin/<BRANCH>` cannot be resolved, when `HEAD` has no commit, or when a changed or graph path
is not valid UTF-8 or contains a line break (it names the path).

#### Scenario: Missing base ref
- **WHEN** `la-affected-tests --base nope` runs and `origin/nope` does not exist
- **THEN** it exits 2 with the shared git error and empty stdout

#### Scenario: Not a git repository
- **WHEN** it runs outside a git repository
- **THEN** it exits 2 with the shared error

#### Scenario: Unborn HEAD
- **WHEN** it runs in a repository without a commit
- **THEN** it exits 2 with the shared error

#### Scenario: Unrepresentable path
- **WHEN** a changed path contains a newline
- **THEN** it exits 2 naming the path and prints nothing on stdout
