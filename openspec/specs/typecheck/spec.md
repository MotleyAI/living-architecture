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
For Python, `la-typecheck` SHALL run the command as configured, apart from the patch preload in its
environment. When the patch applied, it SHALL pass basedpyright's output and its exit codes 0 and 1 through
unchanged and map any higher exit code to 2. In write mode it SHALL append `--writebaseline` and exit 0 after a
successful, patched write. The Python baseline file SHALL be `.basedpyright/baseline.json`.

#### Scenario: Shrink passed through
- **WHEN** a patched Python run fixes a baselined error and adds none
- **THEN** basedpyright's baseline-update message prints and the exit code is 0

#### Scenario: Initial write exits 0
- **WHEN** `la-typecheck --write-baseline` runs on a Python repo with errors and no baseline, and the patch
  applies
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

### Requirement: Python checker is patched
For Python, in check and write mode, `la-typecheck` SHALL run the configured command with a preload added to the
end of the command's `NODE_OPTIONS`, keeping any existing value. When Node compiles basedpyright's CLI bundle, the
preload SHALL remove the condition `!isGetTypeFromCodeFlowPending(referenceKeyWithSymbolId) &&` (microsoft/pyright#11919)
from the compiled source, in the main thread and in every worker thread, and SHALL modify no file. It SHALL patch
only when the bundle's embedded basedpyright version is in the shared contract's verified-version table and the
condition occurs exactly once in the bundle. The run SHALL exit 2 with the shared `typecheck.patch-unverified`
text for an unlisted version, with `typecheck.patch-mismatch` when the condition does not occur exactly once,
and with `typecheck.patch-not-applied` when the command loaded no basedpyright bundle under the preload; the
command's own output SHALL still be relayed. A patched run SHALL print nothing beyond the checker's output. The
verified-version table SHALL initially hold exactly `1.40.2`.

#### Scenario: Dropped diagnostic is reported
- **WHEN** a repo with basedpyright 1.40.2 checks a file whose loop body is `assert k in d, k` followed by a
  type error on `d`
- **THEN** the type error is reported and the exit code is 1

#### Scenario: Worker threads are patched
- **WHEN** the configured command passes `--threads 4` and thirteen files each hold that pattern
- **THEN** all thirteen errors are reported

#### Scenario: Wrapper command
- **WHEN** the configured command starts basedpyright through a wrapper such as `uv run basedpyright`
- **THEN** the patch applies and the run behaves as a direct one

#### Scenario: Existing NODE_OPTIONS kept
- **WHEN** `NODE_OPTIONS` is already set when `la-typecheck` starts
- **THEN** the checker sees the existing value followed by the preload

#### Scenario: Installed checker untouched
- **WHEN** a patched run finishes
- **THEN** every file of the installed basedpyright is byte-identical to before the run

#### Scenario: Unverified version
- **WHEN** the installed basedpyright is 1.39.10
- **THEN** the run exits 2 and stderr names 1.39.10 and the verified versions

#### Scenario: Bundle already patched in place
- **WHEN** the installed 1.40.2 bundle no longer contains the condition
- **THEN** the run exits 2 and stderr reports the condition was found 0 times

#### Scenario: Command does not run basedpyright under Node
- **WHEN** the configured command never loads basedpyright's bundle with the preload, for example because it
  clears `NODE_OPTIONS`
- **THEN** the run exits 2 with the not-applied text after relaying the command's output

#### Scenario: Write mode refused on a patch failure
- **WHEN** `la-typecheck --write-baseline` runs with an unverified basedpyright and no Python baseline
- **THEN** the run exits 2 and no baseline is written

#### Scenario: Patch failure through the npm twin
- **WHEN** a patch failure occurs while `la-typecheck` runs through the npm twin on a mixed repo
- **THEN** stdout, stderr and the exit code are byte-identical to the run through the PyPI twin
