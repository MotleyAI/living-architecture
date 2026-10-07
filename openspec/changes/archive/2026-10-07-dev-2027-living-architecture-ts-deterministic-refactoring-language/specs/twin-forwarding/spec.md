## MODIFIED Requirements

### Requirement: Language-specific commands forward to the native twin
A twin SHALL run a language-specific command natively when the manifest lists its own language for that
command, and otherwise SHALL forward the raw arguments to the twin of the first listed language and exit with
that process's exit code, passing stdout and stderr through unchanged. Neutral commands SHALL never forward.
`dr-refactor`, `dr-compliance` and `dr-mock-lint` are native to both Python and TypeScript; each twin runs
its own language's inputs natively and hands the other language's inputs to the other twin, with the same
working directory, as the refactor capability's routing defines. `la-check-conventions`, `la-count-comments`
and `la-typecheck` are neutral and reach the other language's adapter only through their facts or language
requests. A forwarded process SHALL carry the environment marker `LA_FORWARDED=1`, and a twin that would
forward while the marker is set SHALL exit 2 instead.

#### Scenario: npm twin forwards a Python-only command
- **WHEN** `dr-mock-lint tests` runs through the npm twin in a Python repo with the PyPI twin reachable
- **THEN** the output and exit code equal the PyPI twin's own run

#### Scenario: PyPI twin hands TypeScript inputs to the npm twin
- **WHEN** `dr-refactor rename --file src/a.ts --name foo --new-name bar` runs through the PyPI twin with the npm twin reachable
- **THEN** the output and exit code equal the npm twin's own run

#### Scenario: Other twin unreachable for a dr-* input
- **WHEN** `dr-compliance src/a.ts` runs through the PyPI twin with no npm twin reachable
- **THEN** it exits 2 with the install hint and prints nothing on stdout

#### Scenario: Neutral command never forwards
- **WHEN** `la-config show`, `la-doctor` or `la-arch-diagrams` runs through either twin with the other twin unreachable
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
