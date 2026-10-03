## MODIFIED Requirements

### Requirement: Observable outputs reproduce the conformance goldens
Every case in the conformance corpus SHALL be reproduced byte-exactly: exit code, stdout and stderr, after
normalizing only the temporary repo root to `<ROOT>`. Cases SHALL run in a fixed environment (`LC_ALL=C`,
`TZ=UTC`, a fixed terminal width, fixed git identity and dates) with no network access. A case's `languages`
SHALL name the languages of its fixture, and every listed language's overlay SHALL be applied. Each case SHALL
declare one of three kinds:
- **neutral**: one expected output, independent of fixture language
- **paired**: one variant per listed language, each with its own overlay, and expected outputs that are shared
  or per-language
- **adapter**: one language only

The twin that invokes the command SHALL be chosen independently of the fixture languages, and the expected
output SHALL NOT depend on it. Each twin's own suite SHALL run, through its own entry points, the cases whose
fixture languages are none or only its own language, and whose command that twin implements natively; a
cross-twin run SHALL run every case through each twin's entry points.
`--help` text, parser error wording, and runtime-supplied error detail (OS errors, YAML library messages)
SHALL be excluded from byte comparison; a twin SHALL NOT imitate another runtime's error wording.

#### Scenario: Golden reproduced
- **WHEN** a twin's suite executes a case applicable to it
- **THEN** the exit code, stdout and stderr equal the committed golden byte-for-byte

#### Scenario: Golden drift is reported, not rewritten
- **WHEN** an output differs from its golden during a normal test run
- **THEN** the run fails with a diff and leaves the golden untouched; goldens are written only in the explicit update mode

#### Scenario: Git-history case is deterministic
- **WHEN** a case builds its repo from the declared history (commits, branches, a local bare `origin`, and staged, unstaged, untracked, deleted and renamed files) and runs `la-check-conventions --base main`
- **THEN** the changed-file set and the output equal the golden on every supported Python version

#### Scenario: Cross-twin run
- **WHEN** the cross-twin run executes a TypeScript-fixture case through the PyPI twin and a Python-fixture case through the npm twin
- **THEN** each output equals the case's golden byte-for-byte

#### Scenario: Multi-language fixture
- **WHEN** a case lists `languages: [python, typescript]` with kind `neutral`
- **THEN** both the `python/` and `node/` overlays are applied to one repo before the command runs

#### Scenario: OS error detail is the runtime's own
- **WHEN** `la-arch-check` cannot read `architecture/index.yaml`, or `la-arch-diagrams` cannot read a mapped arc42 doc (missing, or a directory), through either twin
- **THEN** both twins exit with the same code, and stderr starts with the contract prefix (`arch_check: ` / `la-arch-diagrams: `) and names the offending path in the runtime's own wording, with no CPython errno text in the npm twin
