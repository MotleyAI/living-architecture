# twin-forwarding Specification

## Purpose
Lets either twin serve any repo: a twin hands work it cannot do natively to the other twin at the same version
and contract, transparently to the caller, and fails with a clear hint when the other twin is unavailable.

## Requirements

### Requirement: A twin reports its identity
Every twin of each package SHALL accept the internal option `--twin` on its doctor and print exactly one line,
then exit 0. `dr-doctor --twin` SHALL print `<language> <version> <dr-hash>`; `la-doctor --twin` SHALL print
`<language> <version> <la-hash> <dr-hash>`, where `<language>` is the language the twin implements natively
(`python` for the PyPI twin, `typescript` for the npm twin), `<version>` the package version, and each hash the
contract hash of that package's snapshot (for la, the dr hash of the dr library it runs with).

#### Scenario: Identity line
- **WHEN** `dr-doctor --twin` runs through the PyPI twin at version 0.13.0
- **THEN** it prints `python 0.13.0 <dr hash>` and exits 0

#### Scenario: la identity line
- **WHEN** `la-doctor --twin` runs through the npm twin at version 0.13.0
- **THEN** it prints `typescript 0.13.0 <la hash> <dr hash>` and exits 0

### Requirement: The other twin is found by identity
Each package SHALL reach its own other twin: a `dr-*` command the dr twin of language L, an `la-*` command the la
twin of language L. To reach it, a twin SHALL probe, in order, its package's doctor executable (`dr-doctor` or
`la-doctor`) in each directory on `PATH` and then in `<repo>/node_modules/.bin`, skipping directories whose real
path was already probed, the directory whose doctor has the same real path as the invoking twin's own doctor, and
entries that are missing or not executable, and SHALL select the first whose `--twin` line equals the line the
invoking twin expects for L: L, its own version and its own hashes. It SHALL run the requested command by the
absolute path of that directory's executable, with the caller's working directory and environment. If no directory
qualifies it SHALL probe the runner for L declared in the shared languages registry for that package
(`npx -y -p <package>@<version>` for TypeScript, `uvx --from <package>==<version>` for Python, where `<package>` is
`deterministic-refactor` or `living-architecture`) with the doctor's `--twin` and, if the line qualifies, run the
command through the same runner. When the runner is not on `PATH`, or its probe fails or reports a different
identity, the command SHALL exit 2 printing the shared hint that names the missing twin, its package, its version
and its install command.

#### Scenario: Shadowed twin found
- **WHEN** both twins are installed, the npm twin's directory comes first on `PATH`, and a Python-only command runs
- **THEN** the PyPI twin's executable in the later `PATH` directory runs it

#### Scenario: Version or contract mismatch skipped
- **WHEN** the only other twin on `PATH` reports a different version or contract hash
- **THEN** it is not used, and the runner is probed instead

#### Scenario: la twin with a different dr skipped
- **WHEN** the only other la twin on `PATH` reports the same version and la hash but a different dr hash
- **THEN** it is not used, and the runner is probed instead

#### Scenario: Twin unavailable
- **WHEN** no qualifying twin is on `PATH` and the runner is absent or its probe fails
- **THEN** the command exits 2 and stderr names the missing twin, its package, its version and its install command

#### Scenario: dr runner names the dr package
- **WHEN** `dr-refactor` on a TypeScript file runs through the PyPI twin with no npm twin on `PATH`
- **THEN** the probed runner is `npx -y -p deterministic-refactor@<version> dr-doctor --twin`

#### Scenario: Own install not probed
- **WHEN** a twin forwards a command and its own bin directory is on `PATH`
- **THEN** its own doctor is not run

### Requirement: Language-specific commands forward to the native twin
A twin SHALL run a language-specific command natively when the manifest lists its own language for that
command, and otherwise SHALL forward the raw arguments to the twin of the first listed language and exit with
that process's exit code, passing stdout and stderr through unchanged. Neutral commands SHALL never forward.
`dr-refactor`, `dr-compliance` and `dr-mock-lint` are native to both Python and TypeScript; each twin runs
its own language's inputs natively and hands the other language's inputs to the other twin, with the same
working directory, as the refactor capability's routing defines. `la-check-conventions`, `la-count-comments`,
`dr-typecheck`, `la-typecheck` and `la-affected-tests` are neutral and reach the other language's adapter only
through their facts or language requests. A command SHALL run its format check once, in the invoking twin, before
it forwards or requests anything. A forwarded process SHALL carry the environment marker `LA_FORWARDED=1`, and a
twin that would forward while the marker is set SHALL exit 2 instead.

#### Scenario: npm twin forwards a Python-only command
- **WHEN** `dr-mock-lint tests` runs through the npm twin in a Python repo with the PyPI twin reachable
- **THEN** the output and exit code equal the PyPI twin's own run

#### Scenario: PyPI twin hands TypeScript inputs to the npm twin
- **WHEN** `dr-refactor rename --file src/a.ts --symbol foo --new-name bar` runs through the PyPI twin with the npm twin reachable
- **THEN** the output and exit code equal the npm twin's own run

#### Scenario: Other twin unreachable for a dr-* input
- **WHEN** `dr-compliance src/a.ts` runs through the PyPI twin with no npm twin reachable
- **THEN** it exits 2 with the install hint and prints nothing on stdout

#### Scenario: Neutral command never forwards
- **WHEN** `la-config show`, `dr-config show`, `la-doctor`, `dr-doctor` or `la-arch-diagrams` runs through either twin with the other twin unreachable
- **THEN** it completes natively with its usual output

#### Scenario: Conventions gate on own-language files needs no twin
- **WHEN** `la-check-conventions --file src/a.ts` runs through the npm twin with the PyPI twin unreachable
- **THEN** it completes natively with its usual output

#### Scenario: Own-language inputs never forward
- **WHEN** every input of a command is in the invoking twin's own language
- **THEN** no other twin is probed or run

#### Scenario: Forward loop refused
- **WHEN** a twin receives a command it would forward while `LA_FORWARDED=1` is set
- **THEN** it exits 2 without forwarding

#### Scenario: Format refused before forwarding
- **WHEN** the config declares an older format and `dr-refactor` on a TypeScript file runs through the PyPI twin with the npm twin unreachable
- **THEN** it exits 2 with the format refusal and no install hint

#### Scenario: Affected tests of own-language changes need no twin
- **WHEN** `la-affected-tests --base main` runs through the npm twin, only TypeScript files changed, and the PyPI twin is unreachable
- **THEN** it completes natively with its usual output

### Requirement: Architecture facts are exchanged as one schema-checked document
`la-arch-check --language <L> --emit facts` (internal options) SHALL be served only natively: a twin asked for
another language's facts SHALL exit 2 without forwarding. The native twin SHALL print exactly one JSON document to
stdout, valid against the shared facts schema, with its language, version and la contract hash, the existence of
every declared and derived unit of language L (present, missing, or ambiguous with sorted candidate paths), the
top-level units under L's roots, and the measured element-level edges with one witness each; diagnostics SHALL go
to stderr only. A setup error SHALL exit 2 with the usual message on stderr. The requesting twin SHALL relay a
non-zero exit's stderr and exit 2, and SHALL treat as a protocol failure (exit 2 with the shared hint) a document
that is missing, malformed, truncated, invalid against the schema, or whose language, version or la contract hash
differs, and a process ended by a signal.

#### Scenario: Facts request served natively
- **WHEN** the PyPI twin checks a repo declaring `typescript` and the npm twin is reachable
- **THEN** it runs the npm twin's `la-arch-check --language typescript --emit facts` and folds the facts into its report

#### Scenario: Facts request for a non-owned language
- **WHEN** `la-arch-check --language typescript --emit facts` runs through the PyPI twin
- **THEN** it exits 2 without starting any other process

#### Scenario: Forwarded setup error relayed
- **WHEN** the forwarded facts run exits 2 with a tsconfig error on stderr
- **THEN** the invoking `la-arch-check` prints that stderr and exits 2

#### Scenario: Malformed facts
- **WHEN** the forwarded facts run exits 0 but prints invalid JSON
- **THEN** the invoking `la-arch-check` exits 2 with the shared protocol-failure message
