## MODIFIED Requirements

### Requirement: Configuration parameters come from the shared schemas
Every key, type, constraint and default of `living-architecture.yaml` SHALL be defined only by the shared
JSON Schema for that file, every key and type of `architecture/index.yaml` SHALL be defined only by the
shared index schema, and every key and type of a node's model metadata SHALL be defined only by the shared
node schema. A resolved configuration SHALL equal the input with schema defaults filled in
recursively. Filling SHALL also fill absent parent objects, and SHALL keep explicit `false`, `0`, empty
lists and empty strings. A missing file or an empty file SHALL resolve to all defaults. The index schema
SHALL NOT constrain the values whose problems the arch-check reports as findings (`legacy_arrows`,
`diagrams`, `view_depth`).

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

#### Scenario: Node metadata validated by the node schema
- **WHEN** a node's model metadata carries a key the shared node schema does not define
- **THEN** `la-arch-check` exits 2 and its error names the element and the key
