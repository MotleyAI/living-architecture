## MODIFIED Requirements

### Requirement: Applicable languages
`la-typecheck` SHALL check every repo language, as the shared contract defines it, except a language whose
`commands.typecheck` entry is set to `null`. With no applicable language it SHALL print a notice and exit 0.
Outside a git repository it SHALL exit 2.

#### Scenario: Stray script in a Python repo
- **WHEN** a repo with `pyproject.toml` and no `tsconfig.json` tracks `docs/static/app.js`
- **THEN** only Python is checked

#### Scenario: Explicit entry forces a language
- **WHEN** a repo without root markers sets `commands.typecheck.python` to `basedpyright -p python`
- **THEN** Python is checked with that command

#### Scenario: Language turned off
- **WHEN** a repo with `tsconfig.json` and `.ts` files sets `commands.typecheck.typescript` to `null`
- **THEN** TypeScript is not checked
