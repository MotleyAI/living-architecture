# typecheck Specification

## Purpose
`la-typecheck` runs each applicable language's type checker against a committed baseline that only ever shrinks,
under one exit-code contract in both twins.

## Requirements

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

### Requirement: Checker commands
`commands.typecheck` SHALL be a map from language to a command string or `null`, defaulting to `basedpyright`
for Python and `tsc --noEmit` for TypeScript; a plain string SHALL be a configuration error. Command strings SHALL
be split into words by the shared POSIX shell-word rule without a shell. The first word SHALL be looked up in the
language's local bin directory under the repo root (`.venv/bin` for Python, `node_modules/.bin` for TypeScript),
then on `PATH`; the tool's own bundled TypeScript SHALL never be used. A command that is not found SHALL exit 2
with a hint. Commands SHALL run with the repo root as the working directory. The Python command SHALL be
basedpyright-compatible.

#### Scenario: Repo-local tsc preferred
- **WHEN** both `node_modules/.bin/tsc` and a `tsc` on `PATH` exist
- **THEN** the repo-local one runs

#### Scenario: Checker missing
- **WHEN** no `tsc` exists locally or on `PATH`
- **THEN** `la-typecheck` exits 2 and stderr names the command

#### Scenario: String form rejected
- **WHEN** the config sets `commands.typecheck: basedpyright`
- **THEN** loading the configuration fails naming `commands.typecheck`

### Requirement: One report across languages
For each applicable language in language-id order, `la-typecheck` SHALL print a stderr header naming the language
and its command, then that language's output. A language whose twin is not the invoking one SHALL run through
that twin with an internal language option, served only natively, with its stdout and stderr relayed unchanged.
The exit code SHALL be the highest per-language exit code.

#### Scenario: Mixed repo
- **WHEN** a repo has new TypeScript errors and a clean Python run
- **THEN** the Python section prints first, the TypeScript section second, and the exit code is 1

#### Scenario: Same output from either twin
- **WHEN** `la-typecheck` runs through each twin on the same mixed repo
- **THEN** both runs produce byte-identical stdout, stderr and exit codes

### Requirement: Baseline contract
In every language, `la-typecheck` SHALL exit 0 when no error lies outside the baseline, 1 when new errors exist
(listing them), and 2 on a usage, configuration or checker failure. The baseline SHALL shrink only on a run
without new errors. `--write-baseline` SHALL write a baseline for each applicable language that has none (an
empty one for a clean language), SHALL skip with a notice each language whose baseline file exists, and SHALL exit
0 when it wrote at least one baseline and 2 when every applicable language already had one.

#### Scenario: New error and resolved error together
- **WHEN** a run fixes one baselined error and introduces a new one
- **THEN** it exits 1 and the baseline is unchanged

#### Scenario: Write refused when every baseline exists
- **WHEN** `la-typecheck --write-baseline` runs and every applicable language already has its baseline file
- **THEN** it exits 2 and no baseline changes

#### Scenario: Write for a newly added language
- **WHEN** a repo with a Python baseline adds TypeScript and runs `la-typecheck --write-baseline`
- **THEN** the TypeScript baseline is written, Python is skipped with a notice, and the exit code is 0

### Requirement: Python baselines are basedpyright's own
For Python, `la-typecheck` SHALL run the command as configured, passing basedpyright's output and its exit codes
0 and 1 through unchanged and mapping any higher exit code to 2. In write mode it SHALL append `--writebaseline`
and exit 0 after a successful write. The Python baseline file SHALL be `.basedpyright/baseline.json`.

#### Scenario: Shrink passed through
- **WHEN** a Python run fixes a baselined error and adds none
- **THEN** basedpyright's baseline-update message prints and the exit code is 0

#### Scenario: Initial write exits 0
- **WHEN** `la-typecheck --write-baseline` runs on a Python repo with errors and no baseline
- **THEN** the baseline is written and the exit code is 0

### Requirement: TypeScript baseline is a multiset of diagnostics
For TypeScript, `la-typecheck` SHALL run the command with `--pretty false` and parse each
`<file>(<line>,<col>): error TS<code>: <message>` diagnostic with its indented continuation lines, from both
output streams. Each diagnostic SHALL be keyed by the repo-relative POSIX file path, the code and the full
message, independent of line and column. `.tsc-baseline.json` at the repo root SHALL hold the keys with their
counts, sorted by file, code and message, as 2-space-indented JSON with a trailing newline. A key whose current
count exceeds its baseline count SHALL make the run exit 1, listing every current occurrence of that key with its
location and both counts. A run without new errors whose counts dropped SHALL rewrite the baseline downward with a
notice. A diagnostic without a file, a non-zero exit with no diagnostic parsed, or a malformed baseline file SHALL
exit 2, relaying the checker's output.

#### Scenario: Unchanged
- **WHEN** the current diagnostics equal the baseline
- **THEN** the run exits 0 and the baseline file is untouched

#### Scenario: Line shift is not a new error
- **WHEN** a baselined error moves to another line of the same file
- **THEN** the run exits 0

#### Scenario: Count increase
- **WHEN** a key with baseline count 2 now occurs 3 times
- **THEN** the run exits 1 and lists all 3 occurrences with `(baseline 2, now 3)`

#### Scenario: Shrink
- **WHEN** one of two baselined errors is fixed and none is added
- **THEN** the baseline is rewritten with the remaining error and the run exits 0

#### Scenario: Path with spaces and parentheses
- **WHEN** tsc reports an error in `src/my file (copy).ts`
- **THEN** the diagnostic is keyed by that path

#### Scenario: Global diagnostic
- **WHEN** tsc reports `error TS18003: No inputs were found`
- **THEN** the run exits 2 and relays tsc's output
