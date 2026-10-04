## MODIFIED Requirements

### Requirement: The other twin is found by identity
To reach the twin for language L, a twin SHALL probe, in order, the `la-doctor` executable of each directory on
`PATH` and then of `<repo>/node_modules/.bin`, skipping directories whose real path was already probed, the
directory whose `la-doctor` has the same real path as the invoking twin's own `la-doctor`, and entries that are
missing or not executable, and SHALL select the first whose `--twin` line reports L, its own version and its own
contract hash. It SHALL run the requested command by the absolute path of that directory's executable, with the
caller's working directory and environment. If no directory qualifies it SHALL probe the runner for L declared in
the shared languages registry (`npx -y -p living-architecture@<version>` for TypeScript,
`uvx --from living-architecture==<version>` for Python) with `la-doctor --twin` and, if the line qualifies, run
the command through the same runner. When the runner is not on `PATH`, or its probe fails or reports a different
identity, the command SHALL exit 2 printing the shared hint that names the missing twin, its version and its
install command.

#### Scenario: Shadowed twin found
- **WHEN** both twins are installed, the npm twin's directory comes first on `PATH`, and a Python-only command runs
- **THEN** the PyPI twin's executable in the later `PATH` directory runs it

#### Scenario: Version or contract mismatch skipped
- **WHEN** the only other twin on `PATH` reports a different version or contract hash
- **THEN** it is not used, and the runner is probed instead

#### Scenario: Twin unavailable
- **WHEN** no qualifying twin is on `PATH` and the runner is absent or its probe fails
- **THEN** the command exits 2 and stderr names the missing twin, its version and its install command

#### Scenario: Own install not probed
- **WHEN** a twin forwards a command and its own bin directory is on `PATH`
- **THEN** its own `la-doctor` is not run
