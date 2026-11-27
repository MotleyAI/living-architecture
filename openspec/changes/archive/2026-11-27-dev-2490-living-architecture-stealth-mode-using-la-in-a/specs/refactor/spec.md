## MODIFIED Requirements

### Requirement: trmv-mock-lint compares with a base branch
`trmv-mock-lint` SHALL be a parsed command: positional paths and `--base BRANCH`; `--help` SHALL print its help and
exit 0. With `--base`, it SHALL compare with the base ref `BRANCH` resolves to by the shared base resolution, as
`la-affected-tests` does, exiting 2 only when the base ref does not resolve. It SHALL lint the given files as they
are and the same files at the base, read from git without checking anything out (paths mapped through git's rename
detection), and SHALL print only the findings whose count, keyed by path, template and parameters other than the
line, exceeds the base's. The exit code SHALL be 1 iff it prints a finding.

#### Scenario: Help
- **WHEN** `trmv-mock-lint --help` runs through either twin
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

#### Scenario: Remote-tracking base
- **WHEN** `upstream` is a configured remote and `trmv-mock-lint --base upstream/main tests/test_a.py` runs
- **THEN** it compares with `refs/remotes/upstream/main`
