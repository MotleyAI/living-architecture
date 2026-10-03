# twin-forwarding Specification

## Purpose
Lets either twin serve any repo: a twin hands work it cannot do natively to the other twin at the same version
and contract, transparently to the caller, and fails with a clear hint when the other twin is unavailable.

## Requirements

### Requirement: A twin reports its identity
Every twin's `la-doctor` SHALL accept the internal option `--twin` and print exactly one line
`<language> <version> <contract-hash>`, where `<language>` is the language it implements natively (`python` for
the PyPI twin, `typescript` for the npm twin), and exit 0.

#### Scenario: Identity line
- **WHEN** `la-doctor --twin` runs through the PyPI twin at version 0.2.1
- **THEN** it prints `python 0.2.1 <contract hash>` and exits 0

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

### Requirement: Language-specific commands forward to the native twin
A twin SHALL run a language-specific command natively when the manifest lists its own language for that
command, and otherwise SHALL forward the raw arguments to the twin of the first listed language and exit with
that process's exit code, passing stdout and stderr through unchanged. Neutral commands SHALL never forward. In
this release `la-check-conventions`, `la-count-comments`, `dr-refactor`, `dr-compliance` and `dr-mock-lint` are
native to Python only; the PyPI twin SHALL run them as before and SHALL ignore non-Python files as before. A
forwarded process SHALL carry the environment marker `LA_FORWARDED=1`, and a twin that would forward while the
marker is set SHALL exit 2 instead.

#### Scenario: npm twin forwards a Python-only command
- **WHEN** `la-check-conventions --file a.py` runs through the npm twin with the PyPI twin reachable
- **THEN** the output and exit code equal the PyPI twin's own run

#### Scenario: Neutral command never forwards
- **WHEN** `la-config show`, `la-doctor` or `la-arch-diagrams` runs through either twin with the other twin unreachable
- **THEN** it completes natively with its usual output

#### Scenario: Own-language inputs never forward
- **WHEN** every input of a command is in the invoking twin's own language
- **THEN** no other twin is probed or run

#### Scenario: Forward loop refused
- **WHEN** a twin receives a command it would forward while `LA_FORWARDED=1` is set
- **THEN** it exits 2 without forwarding

### Requirement: Architecture facts are exchanged as one schema-checked document
`la-arch-check --language <L> --emit facts` (internal options) SHALL be served only natively: a twin asked for
another language's facts SHALL exit 2 without forwarding. The native twin SHALL print exactly one JSON document to
stdout, valid against the shared facts schema, with its language, version and contract hash, the existence of
every declared and derived unit of language L (present, missing, or ambiguous with sorted candidate paths), the
top-level units under L's root, and the measured element-level edges with one witness each; diagnostics SHALL go
to stderr only. A setup error SHALL exit 2 with the usual message on stderr. The requesting twin SHALL relay a
non-zero exit's stderr and exit 2, and SHALL treat as a protocol failure (exit 2 with the shared hint) a document
that is missing, malformed, truncated, invalid against the schema, or whose language, version or contract hash
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
