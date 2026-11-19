## MODIFIED Requirements

### Requirement: Applicable languages
`dr-typecheck` SHALL check every repo language, as the shared contract defines it, except a language whose
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
- **THEN** `dr-typecheck` exits 2 and stderr names the command

#### Scenario: String form rejected
- **WHEN** the config sets `commands.typecheck: basedpyright`
- **THEN** loading the configuration fails naming `commands.typecheck`

### Requirement: One report across languages
For each applicable language in language-id order, `dr-typecheck` SHALL print a stderr header naming the language
and its command, then that language's output. A language whose twin is not the invoking one SHALL run through
that twin with an internal language option, served only natively, with its stdout and stderr relayed unchanged.
The exit code SHALL be the highest per-language exit code.

#### Scenario: Mixed repo
- **WHEN** a repo has new TypeScript errors and a clean Python run
- **THEN** the Python section prints first, the TypeScript section second, and the exit code is 1

#### Scenario: Same output from either twin
- **WHEN** `dr-typecheck` runs through each twin on the same mixed repo
- **THEN** both runs produce byte-identical stdout, stderr and exit codes

### Requirement: Baseline contract
In every language, `dr-typecheck` SHALL exit 0 when no error lies outside the baseline, 1 when new errors exist
(listing them), and 2 on a usage, configuration or checker failure. The baseline SHALL shrink only on a run
without new errors. Besides shrinking, a check SHALL change a baseline only by realignment under `--realign-from`,
which changes path keys and positions and never the number of entries. `--write-baseline` SHALL write a baseline
for each applicable language that has none (an empty one for a clean language), SHALL skip with a notice each
language whose baseline file exists, and SHALL exit 0 when it wrote at least one baseline and 2 when every
applicable language already had one.

#### Scenario: New error and resolved error together
- **WHEN** a run fixes one baselined error and introduces a new one
- **THEN** it exits 1 and the baseline is unchanged

#### Scenario: Write refused when every baseline exists
- **WHEN** `dr-typecheck --write-baseline` runs and every applicable language already has its baseline file
- **THEN** it exits 2 and no baseline changes

#### Scenario: Write for a newly added language
- **WHEN** a repo with a Python baseline adds TypeScript and runs `dr-typecheck --write-baseline`
- **THEN** the TypeScript baseline is written, Python is skipped with a notice, and the exit code is 0

### Requirement: Python baselines are basedpyright's own
For Python, `dr-typecheck` SHALL run the command as configured, apart from the patch preload in its
environment. When the patch applied, it SHALL pass basedpyright's output and its exit codes 0 and 1 through
unchanged and map any higher exit code to 2. In write mode it SHALL append `--writebaseline` and exit 0 after a
successful, patched write. The Python baseline file SHALL be `.basedpyright/baseline.json`.

#### Scenario: Shrink passed through
- **WHEN** a patched Python run fixes a baselined error and adds none
- **THEN** basedpyright's baseline-update message prints and the exit code is 0

#### Scenario: Initial write exits 0
- **WHEN** `dr-typecheck --write-baseline` runs on a Python repo with errors and no baseline, and the patch
  applies
- **THEN** the baseline is written and the exit code is 0

### Requirement: TypeScript baseline is a multiset of diagnostics
For TypeScript, `dr-typecheck` SHALL run the command with `--pretty false` and parse each
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
For Python, in check and write mode, `dr-typecheck` SHALL run the configured command with a preload added to the
end of the command's `NODE_OPTIONS`, keeping any existing value. When Node compiles basedpyright's CLI bundle, the
preload SHALL remove the condition `!isGetTypeFromCodeFlowPending(referenceKeyWithSymbolId) &&` (microsoft/pyright#11919)
from the compiled source, in the main thread and in every worker thread, and SHALL modify no file. It SHALL patch
only when the bundle's embedded basedpyright version is in the shared contract's verified-version table and the
condition occurs exactly once in the bundle. The run SHALL exit 2 with the shared `typecheck.patch-unverified`
text for an unlisted version, with `typecheck.patch-mismatch` when the condition does not occur exactly once,
and with `typecheck.patch-not-applied` when the command loaded no basedpyright bundle under the preload; the
command's own output SHALL still be relayed. The patch SHALL add no output to a patched run. The
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
- **WHEN** `NODE_OPTIONS` is already set when `dr-typecheck` starts
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
- **WHEN** `dr-typecheck --write-baseline` runs with an unverified basedpyright and no Python baseline
- **THEN** the run exits 2 and no baseline is written

#### Scenario: Patch failure through the npm twin
- **WHEN** a patch failure occurs while `dr-typecheck` runs through the npm twin on a mixed repo
- **THEN** stdout, stderr and the exit code are byte-identical to the run through the PyPI twin

### Requirement: Realignment option
`dr-typecheck` SHALL accept `--realign-from REF`. With `--write-baseline` it SHALL be a usage error, exit 2. A
`REF` that does not name a commit SHALL exit 2 with `typecheck.bad-ref`, before any language header, in both twins.
The TypeScript section SHALL run as a check without the option. A twin running the Python section through the other
twin SHALL pass the option on; the output and exit code SHALL be the same from either twin.

#### Scenario: Bad ref
- **WHEN** `dr-typecheck --realign-from nosuchref` runs
- **THEN** it exits 2, stderr holds only `typecheck.bad-ref` naming `nosuchref`, and no checker runs

#### Scenario: Combined with write
- **WHEN** `dr-typecheck --realign-from HEAD --write-baseline` runs
- **THEN** it exits 2 as a usage error and no baseline changes

#### Scenario: TypeScript repo
- **WHEN** `dr-typecheck --realign-from HEAD` runs in a TypeScript-only repo
- **THEN** stdout, stderr and the exit code equal those of `dr-typecheck` and the baseline is unchanged

#### Scenario: Mixed repo through either twin
- **WHEN** `dr-typecheck --realign-from HEAD` runs through each twin on a mixed repo whose Python baseline needs
  realigning
- **THEN** both runs produce byte-identical stdout, stderr, exit codes and baseline files

### Requirement: Python baseline realignment
For Python, when the baseline file exists, `dr-typecheck --realign-from REF` SHALL realign the baseline and then
run the check, whose result is the section's output and exit code. Without a baseline file the section SHALL be a
plain check.

Realignment SHALL treat `REF` as a commit where the baseline matched:

- Each file git reports as renamed between `REF` and the working tree SHALL have its entries moved from the old
  path key to the new one, merged in position order with entries the new key already holds. A destination git does
  not track SHALL NOT be followed.
- The files considered SHALL be those the baseline lists, by their new path, that exist and whose text differs from
  their text at `REF` or that were renamed. With none, nothing is realigned.
- The diagnostics the baseline does not match and the entries no diagnostic matches SHALL be found by running the
  configured checker on those files against copies; the checker SHALL NOT write the project's baseline.
- An unmatched diagnostic SHALL take an unmatched entry of its file only when the entry's code equals the
  diagnostic's rule, the entry's columns and line count equal the diagnostic's range mapped back to the text at
  `REF`, and the entry's place in the list is consistent with the order of the diagnostics at `REF` (after every
  entry of an earlier diagnostic, before every entry of a later one). The mapping SHALL be the one `dr-refactor`
  uses, in UTF-16 columns. A diagnostic whose range maps back to an empty range SHALL take no entry.
- Each taken entry SHALL get its diagnostic's current columns and line count and stay in position order. Every
  other entry SHALL be kept unchanged, so the number of entries is the same.

When a key or an entry changed, the baseline SHALL be written in basedpyright's format before the check and stderr
SHALL hold `typecheck.realign` with the number of entries that moved or changed; otherwise the file SHALL stay
byte-identical and nothing is printed. The written baseline SHALL stand whatever the check then returns. A malformed
baseline SHALL exit 2 with `typecheck.baseline-invalid`; a checker or patch failure while realigning SHALL exit 2
with the text a check gives for it, the baseline untouched.

#### Scenario: Edit earlier on the line
- **WHEN** a line holds two baselined `reportArgumentType` errors, an earlier argument on it is wrapped in a call
  so both shift by five columns, and `dr-typecheck --realign-from HEAD` runs with the edit uncommitted
- **THEN** both entries get the new columns, stderr holds `typecheck.realign` with count 2, and the exit code is 0

#### Scenario: Committed edit
- **WHEN** the same edit is committed and `dr-typecheck --realign-from HEAD~1` runs
- **THEN** the baseline and the output are as for the uncommitted edit, with `HEAD~1` named

#### Scenario: Realigned entry beside a new error
- **WHEN** one baselined line is edited so its error shifts, and another line gains a new error
- **THEN** the shifted entry is realigned and written, the new error is reported, and the exit code is 1

#### Scenario: New error inside added text
- **WHEN** a baselined error is fixed and a new error of the same rule lies wholly in text added since `REF`
- **THEN** no entry is realigned, the baseline is unchanged, the new error is reported and the exit code is 1

#### Scenario: Same-shaped new error out of order
- **WHEN** a baselined error is fixed, and a new error of the same rule, whose range maps back to the fixed error's
  columns, lies after a later error that is still matched
- **THEN** the fixed error's entry is not taken, the new error is reported and the exit code is 1

#### Scenario: Renamed and edited file
- **WHEN** a file with baseline entries is renamed with `git mv`, a baselined line in it is edited, and
  `dr-typecheck --realign-from HEAD` runs
- **THEN** its entries sit under the new path key with the new columns and the exit code is 0

#### Scenario: Renamed file only
- **WHEN** a file with baseline entries is renamed with `git mv` and not edited
- **THEN** its entries sit under the new path key unchanged and the exit code is 0

#### Scenario: Rename onto a key with entries
- **WHEN** the baseline already holds entries under a rename's new path
- **THEN** the key holds both sets of entries in position order

#### Scenario: Nothing to realign
- **WHEN** no baseline-listed file changed since `REF`
- **THEN** stdout, stderr and the exit code equal those of `dr-typecheck` and the baseline is byte-identical

#### Scenario: Character outside the BMP before the edit
- **WHEN** a baselined line holds an emoji in a string before the edited text and the error
- **THEN** the entry gets the error's current UTF-16 columns

#### Scenario: Checker fails while realigning
- **WHEN** the configured checker exits 2 on the realignment run
- **THEN** `dr-typecheck` exits 2 with the checker-failure text and the baseline is unchanged

#### Scenario: Malformed baseline
- **WHEN** `.basedpyright/baseline.json` is not valid JSON and `dr-typecheck --realign-from HEAD` runs
- **THEN** it exits 2 with `typecheck.baseline-invalid` naming `python`

### Requirement: Realignment hint
A Python check without `--realign-from` and without `--write-baseline` that exits 1 while the Python baseline file
exists SHALL print `typecheck.realign-hint` on stderr after the checker's output. No other run SHALL print it.

#### Scenario: New error with a baseline
- **WHEN** `dr-typecheck` runs on a Python repo with a baseline file and an error outside it
- **THEN** stderr ends with `typecheck.realign-hint` and the exit code is 1

#### Scenario: New error without a baseline
- **WHEN** `dr-typecheck` runs on a Python repo with errors and no baseline file
- **THEN** the hint is not printed

#### Scenario: Failing realign run
- **WHEN** `dr-typecheck --realign-from HEAD` exits 1
- **THEN** the hint is not printed

## ADDED Requirements

### Requirement: la-typecheck is a deprecated alias for one minor version
The `living-architecture` package SHALL install `la-typecheck` through 0.13.x and SHALL NOT install it from 0.14.0 on.
It SHALL accept exactly the options of `dr-typecheck`, behave as `dr-typecheck` with the same arguments, and
produce byte-identical stdout and the same exit code. Before any other output it SHALL print exactly one line on
stderr, rendered from the shared findings registry, naming `dr-typecheck` and `0.14.0` as the release that removes
the alias; the rest of stderr SHALL equal `dr-typecheck`'s. A process carrying `LA_FORWARDED=1` SHALL NOT print the
line, so a forwarded language section never repeats it. `--help` and usage errors SHALL behave as `dr-typecheck`'s,
without the line.

#### Scenario: Alias matches the renamed command
- **WHEN** `la-typecheck` and `dr-typecheck` run through the same twin on the same repo with new errors
- **THEN** stdout and the exit code are byte-identical, and the alias's stderr is the deprecation line followed by `dr-typecheck`'s stderr

#### Scenario: Deprecation line printed once on a mixed repo
- **WHEN** `la-typecheck` runs through the PyPI twin on a mixed repo with the npm twin reachable
- **THEN** stderr carries the deprecation line exactly once, before the Python section header

#### Scenario: Write mode through the alias
- **WHEN** `la-typecheck --write-baseline` runs in a repo with no baseline
- **THEN** the baseline is written exactly as `dr-typecheck --write-baseline` writes it and the exit code is 0

#### Scenario: Alias help
- **WHEN** `la-typecheck --help` runs
- **THEN** it exits 0 and prints no deprecation line
