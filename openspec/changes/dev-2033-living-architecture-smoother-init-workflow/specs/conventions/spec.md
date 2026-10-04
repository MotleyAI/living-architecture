## ADDED Requirements

### Requirement: The conventions gate enforces only the configured rules
`la-check-conventions` SHALL report findings only for rules listed in `conventions.rules`. With an empty
list it SHALL report no rule findings and exit 0. A file's `unreadable` or `syntax-error` finding SHALL be
reported iff at least one configured rule applies to that file. A waiver comment for a rule that is not
configured SHALL have no effect.

#### Scenario: One rule dropped
- **WHEN** the config sets `conventions.rules: [import-not-top]` and a changed source file breaches the text-ratio cap and has an import inside a function
- **THEN** only the `import-not-top` finding is reported and the command exits 1

#### Scenario: Test-only rules dropped
- **WHEN** the config sets `conventions.rules: [import-not-top, text-ratio]` and a changed test file has `assert a and b`
- **THEN** no `composite-assert` finding is reported

#### Scenario: Gate off
- **WHEN** the config sets `conventions.rules: []` and a changed file breaches every rule
- **THEN** the command reports nothing and exits 0

#### Scenario: Syntax error with the gate off
- **WHEN** the config sets `conventions.rules: []` and a changed `.py` file does not parse
- **THEN** no `syntax-error` finding is reported and the command exits 0

#### Scenario: Syntax error with a rule on
- **WHEN** the config sets `conventions.rules: [text-ratio]` and a changed `.py` file does not parse
- **THEN** the `syntax-error` finding is reported and the command exits 1

#### Scenario: Default keeps every rule
- **WHEN** the config does not set `conventions.rules` and a changed test file has `assert a and b`
- **THEN** the `composite-assert` finding is reported

#### Scenario: TypeScript test file
- **WHEN** the config sets `conventions.rules: [text-ratio]` and a changed `src/a.test.ts` has `expect(a && b).toBe(true)`
- **THEN** no `composite-assert` finding is reported
