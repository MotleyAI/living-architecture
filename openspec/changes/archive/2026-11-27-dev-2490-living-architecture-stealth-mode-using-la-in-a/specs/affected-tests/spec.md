## MODIFIED Requirements

### Requirement: The command prints the affected test files of a change against a base branch
`la-affected-tests --base BRANCH` SHALL compare the working tree with the base ref `BRANCH` resolves to by the shared
base resolution (exactly as `la-check-conventions --base`), and print on stdout every selected test
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

#### Scenario: Fork compared with its upstream
- **WHEN** a repo has remotes `origin` and `upstream`, `upstream/main` has a commit `origin/main` lacks, and `la-affected-tests --base upstream/main` runs
- **THEN** the changed set is computed against the merge base with `upstream/main`

### Requirement: Setup and git failures exit 2
The command SHALL exit 2 with a shared message on stderr and nothing on stdout when it runs outside a git
repository, when the base ref cannot be resolved, when `HEAD` has no commit, or when a changed or graph path
is not valid UTF-8 or contains a line break (it names the path).

#### Scenario: Missing base ref
- **WHEN** `la-affected-tests --base nope` runs and `origin/nope` does not exist
- **THEN** it exits 2 with the shared git error and empty stdout

#### Scenario: Missing remote-tracking base ref
- **WHEN** `la-affected-tests --base upstream/nope` runs, `upstream` is a remote and `upstream/nope` does not exist
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

## ADDED Requirements

### Requirement: Shared base resolution
Every `--base BRANCH` option (`la-affected-tests`, `la-check-conventions`, `la-leak-check`, `trmv-mock-lint`,
`trmv-typecheck`) SHALL resolve one base ref the same way: when `BRANCH` is `<remote>/<rest>`, `<remote>` is a
configured git remote and `<rest>` is not empty, the base ref SHALL be `refs/remotes/<remote>/<rest>` after a
best-effort, bounded, non-prompting `git fetch <remote> <rest>`; otherwise it SHALL be `origin/<BRANCH>` after the
same fetch from `origin`, as before. The base ref not resolving SHALL be the command's git error (exit 2).

#### Scenario: Plain branch name
- **WHEN** `--base main` is passed and `main` is not prefixed by a remote name
- **THEN** the base ref is `origin/main`

#### Scenario: Branch with a slash on origin
- **WHEN** `--base feature/x` is passed and no remote is named `feature`
- **THEN** the base ref is `origin/feature/x`

#### Scenario: Remote-tracking ref
- **WHEN** `--base upstream/main` is passed and `upstream` is a configured remote
- **THEN** the base ref is `refs/remotes/upstream/main`, fetched from `upstream`
