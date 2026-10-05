## ADDED Requirements

### Requirement: la-doctor checks the tools against the calling plugin
`la-doctor --plugin DIR` SHALL resolve DIR against the working directory and read the nearest
`.claude-plugin/plugin.json` file at or above it. When none exists it SHALL report `doctor.plugin-not-found`;
when the file is not valid UTF-8 JSON (no BOM, no `NaN`/`Infinity`) whose top level is an object with a string
`version` free of lone surrogates, it SHALL report `doctor.plugin-invalid`; when that version differs from the installed tools' version
it SHALL report `doctor.version-mismatch`. Given both `--expect` and `--plugin`, each SHALL be checked,
`--expect` first. Every skill that uses an `la-*` or `dr-*` command SHALL run
`la-doctor --plugin <this skill's base directory>` as its preflight and SHALL NOT pin a version.

#### Scenario: Version read from the enclosing plugin
- **WHEN** `la-doctor --plugin <plugin>/skills/pr` runs and `<plugin>/.claude-plugin/plugin.json` declares the installed version
- **THEN** it reports healthy and exits 0

#### Scenario: Plugin version differs
- **WHEN** the nearest `plugin.json` declares `0.0.0`
- **THEN** it prints the `doctor.version-mismatch` problem and exits 1

#### Scenario: No plugin manifest
- **WHEN** no `.claude-plugin/plugin.json` exists at or above DIR
- **THEN** it prints `no .claude-plugin/plugin.json at or above <DIR>` and exits 1

#### Scenario: Skill pins a version
- **WHEN** a SKILL.md contains `la-doctor --expect`
- **THEN** the skills test fails
