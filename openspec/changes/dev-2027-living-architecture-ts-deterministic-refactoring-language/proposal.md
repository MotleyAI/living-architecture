## Why

PR 4 of 4 under DEV-1990. The npm twin checks TS/JS repos but still forwards every `dr-*` command to the
PyPI twin, so a TS repo has no verified refactoring and no Python-free path. The skills hard-code Python
idioms (basedpyright, rope, `TYPE_CHECKING`, `*.py`), so an agent working in a TS repo is told Python things.
This change closes DEV-1990: native TS refactoring, language-neutral skills, the README's TS claims, the first
public npm release and the acceptance runs.

## What Changes

- The npm twin implements `dr-refactor`, `dr-compliance` and `dr-mock-lint` natively for TS/JS, driving the
  bundled TypeScript LanguageService. Both twins are native for their own language and route each input file
  to its language's twin; mixed `dr-compliance` / `dr-mock-lint` runs print one block per language.
- `dr-compliance` check sets become per-language registry facts; TS checks are `tsconfig`, `explicit-any`,
  `untyped-def` and `mock`. `--select` loses its literal default (absent = every check of each file's
  language).
- TS `dr-mock-lint` flags untyped `vi.fn()`/`jest.fn()`, untyped module-mock factories and double assertions
  in test files.
- One definition of the repo's languages, shared by `la-typecheck`, `la-config` and `la-doctor`.
- `la-config get languages` and `la-config get lang.<language>.<key>` serve curated language facts to skills.
- `la-doctor` requires `node` and `npx` when TypeScript is a repo language.
- Skills become language-neutral: facts via `la-config`, idioms in `plugin/languages/<language>.md`, a leak
  test in both suites. Init measures the AS-IS graph with an `la-arch-check` bootstrap loop and wires
  `la-typecheck --write-baseline`; the CI snippet comes in `uvx` and `npx` forms.
- README and AGENTS.md describe both twins; version 0.3.0; the npm package becomes public.
- A Node-only container acceptance run in CI with a PATH trap for `python`, `python3`, `uv` and `uvx`.

## Capabilities

### New Capabilities
- `refactor`: the `dr-refactor`, `dr-compliance` and `dr-mock-lint` behaviour for TypeScript, routing by file
  language, and the shared refactor output format.

### Modified Capabilities
- `twin-forwarding`: `dr-*` commands are native to both twins and routed by the language of their inputs.
- `typecheck`: "Applicable languages" is defined on the repo's languages.
- `shared-contract`: repo languages, `la-config` language keys, `la-doctor` executables per language, and
  language-neutral skills.

## Impact

- `shared/`: `cli.yaml` (`native`, `--select`), `languages.yaml` (`compliance_checks`, `declaration_globs`,
  `excluded_dirs`), `findings.yaml` (TS refactor, compliance and mock-lint texts), new vectors
  (`diff.yaml`, `skill-leaks.yaml`).
- npm twin: new `src/refactor` node; `config`, `doctor`, `cli`, `typecheck` touched. PyPI twin: `refactor`
  routing, `config`, `doctor`, `typecheck`.
- `architecture/`: new `typescript.refactor` node and arrows, regenerated diagrams.
- `plugin/`: every skill with language idioms; new `plugin/languages/`.
- CI: a Node-only acceptance job. Release: 0.3.0, `node/package.json` no longer private.
- Python repos: every existing conformance golden stays byte-identical.
