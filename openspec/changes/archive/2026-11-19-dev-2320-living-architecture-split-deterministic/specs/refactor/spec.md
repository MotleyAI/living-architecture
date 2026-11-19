## MODIFIED Requirements

### Requirement: Refactors keep the type-check baseline aligned
Every `dr-refactor` subcommand SHALL keep the baseline of each language it edits aligned, when that language's
`commands.typecheck` entry is set and its `baseline_file` exists at the repo root and lists a file the refactor
affects. A baselined diagnostic that the refactor moves, by an edit on its line, a moved file or a moved
declaration, SHALL stay baselined; no diagnostic SHALL become baselined that was not. The baseline SHALL appear in
the printed diff in dry-run and `--apply` alike, and with `--apply` be written with the sources. Diagnostic ranges SHALL be mapped
through the refactor's edits: a start at or inside a replaced span SHALL map to the replacement's start, an end
inside or at the end of one to the replacement's end; at an insertion point a start SHALL map after the inserted
text and an end before it, and an empty range SHALL map both ends as its start.

- Python (`.basedpyright/baseline.json`): the baselined diagnostics and the entries they match SHALL be those
  basedpyright itself matches, from running the configured command over the affected files once with a temporary
  copy of the baseline and once with an empty one; the project's baseline SHALL NOT be written by the checker. Each
  matched entry whose file, columns or line count change SHALL be rewritten in place, or inserted at its sorted
  position in its new file. The configured command SHALL first be probed in the `checks` phase, run once on one source
  of the refactor, so a command that cannot run refuses before any reference search.
- TypeScript (`.tsc-baseline.json`): the before and after diagnostics SHALL be the pre-emit diagnostics, from the
  bundled language services of every project holding the file, of every file the baseline lists, before and after
  the edits applied in memory, keyed as `dr-typecheck` keys tsc's output. A baselined key whose instances all map to
  one new key SHALL move its count there.

A diagnostic whose range cannot be mapped, or a TypeScript key whose instances map to different keys while only
some are baselined, SHALL leave its entry unchanged and print `refactor.baseline-ambiguous` on stderr, without
changing the exit code. A checker run that fails SHALL exit 1 with `refactor.baseline-failed` naming the language,
followed by the checker's cause, and write nothing.

#### Scenario: Rename shifts baselined columns
- **WHEN** a line holds a baselined `reportArgumentType` error after a call of `get_model`, and `get_model` is
  renamed to `load` with `--apply`
- **THEN** that entry's columns shift by the length difference, every other entry is unchanged, and `dr-typecheck`
  passes afterwards

#### Scenario: Dry-run shows the baseline
- **WHEN** the same rename runs without `--apply`
- **THEN** the diff of `.basedpyright/baseline.json` is printed with the source diffs and nothing is written

#### Scenario: Matching follows basedpyright
- **WHEN** a file's baseline holds two identical-shaped entries, a stale entry, and an entry for a diagnostic below a
  newly unbaselined one, and a rename edits those lines
- **THEN** exactly the entries basedpyright matched are rewritten, and `dr-typecheck` reports the same new errors
  as before the rename

#### Scenario: Configured command with a project flag
- **WHEN** `commands.typecheck.python` is `basedpyright -p .` and the rename edits a baselined line
- **THEN** the entry is realigned

#### Scenario: Moved module
- **WHEN** `move-module` moves `pkg/a.py`, which has baseline entries, into `pkg/sub/`
- **THEN** those entries are listed under `./pkg/sub/a.py` and `dr-typecheck` passes

#### Scenario: Moved declaration
- **WHEN** `move-symbol` moves a function with a baselined error into another file that has entries of its own
- **THEN** the entry moves to the destination file at its sorted position

#### Scenario: TypeScript message names the symbol
- **WHEN** an unedited `src/c.ts` has a baselined `TS2322` whose message names type `Old`, and `Old` is renamed to
  `New`
- **THEN** the key's count moves to the message naming `New`, and real `tsc` reproduces that key

#### Scenario: Ambiguous split
- **WHEN** a TypeScript key has two instances, one baselined, whose messages change differently
- **THEN** the key is unchanged, stderr holds `refactor.baseline-ambiguous` naming it, and the exit code is 0

#### Scenario: No baseline
- **WHEN** the repo has no baseline file, or `commands.typecheck.python` is null
- **THEN** no checker runs, no `[baseline]` line is printed, and the output equals the rename without alignment

#### Scenario: Checker failure
- **WHEN** the configured command cannot run
- **THEN** stderr ends with `refactor.baseline-failed` naming `python` and its cause, the exit code is 1 and nothing
  is written
