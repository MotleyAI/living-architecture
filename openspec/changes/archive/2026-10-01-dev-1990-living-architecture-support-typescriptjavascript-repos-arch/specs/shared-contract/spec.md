## Purpose

The single contract both native implementations (the PyPI and npm twins) obey. Parameters, defaults,
user-facing wording and the command surface are defined once as shared data. A conformance corpus pins every
observable output so the twins cannot drift.

## ADDED Requirements

### Requirement: Configuration parameters come from the shared schemas
Every key, type, constraint and default of `living-architecture.yaml` SHALL be defined only by the shared
JSON Schema for that file, and every key and type of `architecture/index.yaml` SHALL be defined only by the
shared index schema. A resolved configuration SHALL equal the input with schema defaults filled in
recursively. Filling SHALL also fill absent parent objects, and SHALL keep explicit `false`, `0`, empty
lists and empty strings. A missing file or an empty file SHALL resolve to all defaults. The index schema
SHALL NOT reject any input that the arch-check reports as a finding today.

#### Scenario: Missing config resolves to schema defaults
- **WHEN** a repo has no `living-architecture.yaml` and `la-config show` runs
- **THEN** it prints the resolved configuration built only from the schema defaults, byte-identical to the frozen golden, and exits 0

#### Scenario: Partial nested config is completed
- **WHEN** the config sets only `reviewers: {sonar: {enabled: false}}` and `la-config show` runs
- **THEN** every other key, including `reviewers.coderabbit` and `reviewers.sonar.project_key`, carries its schema default

#### Scenario: Explicit falsy values are kept
- **WHEN** the config sets `conventions: {exempt: []}` and `reviewers: {coderabbit: false}`
- **THEN** the resolved configuration keeps the empty list and `false` rather than substituting defaults

#### Scenario: Unknown key is rejected
- **WHEN** the config contains a key the schema does not define and `la-config show` runs
- **THEN** the command exits 1 and its error names the offending key

#### Scenario: Cross-field rule is enforced
- **WHEN** the config sets `reviewers.sonar.enabled: true` without `project_key`
- **THEN** validation fails, the command exits with the configuration-error code, and the error names `project_key`

#### Scenario: A finding-level index problem stays a finding
- **WHEN** `index.yaml` sets `legacy_arrows.baseline: -1` and `la-arch-check` runs
- **THEN** it reports the `baseline-ratchet` finding and exits 1, exactly as the frozen golden records, not a schema error with exit 2

### Requirement: YAML is read with one fixed profile
Every YAML input SHALL be read as YAML 1.1, exactly as PyYAML's safe loader reads it: `yes`/`no`/`on`/`off`
are booleans, and a duplicate mapping key takes the last value.

#### Scenario: YAML 1.1 boolean
- **WHEN** the config sets `reviewers: {coderabbit: yes}`
- **THEN** the resolved `reviewers.coderabbit` is `true`

#### Scenario: Duplicate key
- **WHEN** a mapping in the config repeats a key
- **THEN** the last occurrence wins and no error is raised

### Requirement: Issue-key patterns use the portable regex subset
`issue_key_pattern` SHALL be accepted only when it uses the portable subset documented in the contract:
- literals
- character classes including `\d`, `\w`, `\s`
- quantifiers including `{m,n}`
- anchors
- groups
- alternation

Lookbehind, named groups, inline flags, and possessive or atomic constructs SHALL be rejected as a
configuration error. Accepted patterns SHALL be applied with full-match semantics.

#### Scenario: Default pattern accepted
- **WHEN** no `issue_key_pattern` is configured
- **THEN** the default `[A-Z][A-Z0-9]+-\d+` is used and `[target: ABC-123]` tags are accepted

#### Scenario: Non-portable construct rejected
- **WHEN** `issue_key_pattern` is `(?<=X)[A-Z]+-\d+`
- **THEN** loading the configuration fails with a configuration error naming `issue_key_pattern`

### Requirement: User-facing texts come from the shared findings registry
Every finding line, gate verdict and hint that a command prints SHALL be rendered from a template in the
shared findings registry, identified by a stable id. A `{name}` placeholder SHALL insert the value as text.
A `{name!r}` placeholder SHALL insert the canonical repr defined by the contract. That repr covers only
normalized values (string, integer, float, boolean, null, list, mapping). It SHALL match Python's `repr`
for those values, including quote selection and escapes, and it is pinned by shared test vectors. Every
registry template SHALL be exercised by at least one conformance case.

#### Scenario: Registry coverage
- **WHEN** the test suite runs
- **THEN** it fails if any template id in the findings registry is not produced by at least one conformance golden

#### Scenario: Repr of a string containing a quote
- **WHEN** a `!r` placeholder receives the string `it's`
- **THEN** it renders as `"it's"`, matching the shared repr vector

#### Scenario: Repr of a non-scalar YAML value
- **WHEN** `index.yaml` sets `legacy_arrows.baseline: [1, 2]`
- **THEN** the `baseline-ratchet` finding renders the value as `[1, 2]`, byte-identical to the frozen golden

### Requirement: Command surfaces come from the shared CLI manifest
The set of `la-*` and `dr-*` commands, and each command's subcommands, options, types, choices, repeatability,
required options and positionals, SHALL be defined by the shared CLI manifest. Each installed command SHALL
build its parser from it. Parsing SHALL accept no abbreviated long options and SHALL honour `--`. A usage
error SHALL exit 2. A command declared `passthrough` SHALL hand its raw arguments to its handler. The
package's installed entry points SHALL be exactly the manifest's command set, and every command a skill
references SHALL be in the manifest.

#### Scenario: Entry points match the manifest
- **WHEN** the test suite runs
- **THEN** it fails if the package's console scripts differ from the manifest's commands in either direction

#### Scenario: Abbreviated option rejected
- **WHEN** `la-check-conventions --bas main` runs
- **THEN** it exits 2 as a usage error

#### Scenario: Accepted invocation vector
- **WHEN** `la-check-conventions --file a.py --file b.py --exclude 'gen/*'` runs
- **THEN** both files are checked, `gen/*` is exempt, and the exit code and stdout equal the golden

#### Scenario: Skill references only real commands
- **WHEN** a SKILL.md mentions an `la-*` or `dr-*` command absent from the manifest
- **THEN** the skills test fails naming the command

### Requirement: Test-file classification uses the shared glob dialect
Classifying a file as a test file SHALL use the test globs that the shared languages registry declares for
the language. Matching SHALL use the contract's single glob dialect:
- matched against the POSIX repo-relative path
- case-sensitive
- `*` matches within one path segment
- `**` matches zero or more whole segments

For Python, classification SHALL give the same result as today for every path.

#### Scenario: Python test-file parity
- **WHEN** the classifier runs over the shared vector set (including `tests/x.py`, `a/test/b.py`, `test_x.py`, `pkg/x_test.py`, `conftest.py`, `testing/x.py`, `atest_x.py`, `Tests/x.py`)
- **THEN** each result equals the pre-restructure classification recorded in the vectors

### Requirement: Vendored contract snapshots match the shared source
Each package SHALL load its contract only from its own vendored snapshot of `shared/`. The snapshot SHALL be
byte-identical to `shared/`, with file modes preserved, and SHALL carry a contract hash. `la-doctor` SHALL
report that hash.

#### Scenario: Stale snapshot detected
- **WHEN** a file under `shared/` changes and the snapshot is not re-synced
- **THEN** the test suite fails and names the sync command

#### Scenario: Built artifact carries the contract
- **WHEN** the wheel is built and installed into a clean environment outside the checkout
- **THEN** every command loads its contract, a review shim runs its bundled script, and `la-doctor` reports the same contract hash as the source tree

### Requirement: Observable outputs reproduce the conformance goldens
Every case in the conformance corpus SHALL be reproduced byte-exactly: exit code, stdout and stderr, after
normalizing only the temporary repo root to `<ROOT>`. Cases SHALL run in a fixed environment (`LC_ALL=C`,
`TZ=UTC`, a fixed terminal width, fixed git identity and dates) with no network access. Each case SHALL
declare one of three kinds:
- **neutral**: one expected output, run by every twin
- **paired**: a per-language fixture overlay, with expected outputs that are shared or per-language
- **adapter**: one language only

`--help` text and parser error wording SHALL be excluded from byte comparison.

#### Scenario: Golden reproduced
- **WHEN** the Python conformance runner executes a case applicable to Python
- **THEN** the exit code, stdout and stderr equal the committed golden byte-for-byte

#### Scenario: Golden drift is reported, not rewritten
- **WHEN** an output differs from its golden during a normal test run
- **THEN** the run fails with a diff and leaves the golden untouched; goldens are written only in the explicit update mode

#### Scenario: Git-history case is deterministic
- **WHEN** a case builds its repo from the declared history (commits, branches, a local bare `origin`, and staged, unstaged, untracked, deleted and renamed files) and runs `la-check-conventions --base main`
- **THEN** the changed-file set and the output equal the golden on every supported Python version
