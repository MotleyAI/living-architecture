## ADDED Requirements

### Requirement: Repo languages
A registered language SHALL be a repo language when its `commands.typecheck` entry is set explicitly to a
command, or when the repo has one of the language's marker files at the root and at least one file of that
language (tracked, or untracked and not ignored, minus `conventions.exempt`). Every command that depends on the
repo's languages SHALL use this one definition.

#### Scenario: Stray script is not a language
- **WHEN** a repo with `pyproject.toml` and no `tsconfig.json` tracks `docs/static/app.js`
- **THEN** the repo languages are `python` only

#### Scenario: Typecheck turned off keeps the language
- **WHEN** a repo with `tsconfig.json` and `.ts` files sets `commands.typecheck.typescript` to `null`
- **THEN** `typescript` is still a repo language

### Requirement: Language facts through la-config
`la-config get languages` SHALL print the repo languages as a JSON list in registry id order, and SHALL exit 2
outside a git repository. `la-config get lang.<language>.<key>` SHALL print a registry fact for any registered
language, for the public keys `source_extensions`, `source_globs`, `test_globs`, `declaration_globs`,
`comment_prefix`, `suppression`, `waiver`, `baseline_file` and `markers`. `source_globs` SHALL be one glob per
source extension in the contract glob dialect, and `waiver` the language's waiver comment
(`<comment prefix> ALLOW(<rule>): <reason>`). Lists SHALL print as JSON and strings as text. Any other
language or key SHALL exit 2 with the unknown-key message. `la-config show` SHALL be unchanged.

#### Scenario: Repo languages of a mixed repo
- **WHEN** `la-config get languages` runs in a repo with Python and TypeScript files and both markers
- **THEN** it prints `["python", "typescript"]`

#### Scenario: A fact for a language the repo lacks
- **WHEN** `la-config get lang.typescript.suppression` runs in a Python-only repo
- **THEN** it prints `// @ts-expect-error — <reason>`

#### Scenario: Internal registry field refused
- **WHEN** `la-config get lang.python.runner` runs
- **THEN** it exits 2 with the unknown-key message

### Requirement: Doctor checks each repo language's executables
`la-doctor` SHALL report a missing executable for `node` and for `npx` when TypeScript is a repo language.
Outside a git repository it SHALL skip the language-dependent checks. A repo without TypeScript SHALL get
today's output.

#### Scenario: TypeScript repo without node
- **WHEN** `la-doctor` runs in a TypeScript repo with no `node` on PATH
- **THEN** it reports `node` missing and exits 1

#### Scenario: Python repo unchanged
- **WHEN** `la-doctor` runs in a Python-only repo with no `node` on PATH
- **THEN** its output equals today's golden

### Requirement: Skills are language-neutral
A SKILL.md SHALL contain no language-only token from the shared skill-leak list; language idioms SHALL live
only in `plugin/languages/<language>.md`. Every `la-config get <key>` a SKILL.md names SHALL be a valid key
(with `<language>` standing for any registered language). Both twins' suites SHALL enforce these rules.

#### Scenario: Leaked token
- **WHEN** a SKILL.md mentions `basedpyright`
- **THEN** the skills test fails in both suites naming the skill and the token

#### Scenario: Unknown config key
- **WHEN** a SKILL.md says `la-config get lang.<language>.runner`
- **THEN** the skills test fails naming the key
