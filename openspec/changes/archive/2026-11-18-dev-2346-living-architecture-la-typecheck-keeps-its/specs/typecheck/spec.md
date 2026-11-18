## MODIFIED Requirements

### Requirement: Baseline contract
In every language, `la-typecheck` SHALL exit 0 when no error lies outside the baseline, 1 when new errors exist
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
- **WHEN** `la-typecheck --write-baseline` runs and every applicable language already has its baseline file
- **THEN** it exits 2 and no baseline changes

#### Scenario: Write for a newly added language
- **WHEN** a repo with a Python baseline adds TypeScript and runs `la-typecheck --write-baseline`
- **THEN** the TypeScript baseline is written, Python is skipped with a notice, and the exit code is 0

## ADDED Requirements

### Requirement: Realignment option
`la-typecheck` SHALL accept `--realign-from REF`. With `--write-baseline` it SHALL be a usage error, exit 2. A
`REF` that does not name a commit SHALL exit 2 with `typecheck.bad-ref`, before any language header, in both twins.
The TypeScript section SHALL run as a check without the option. A twin running the Python section through the other
twin SHALL pass the option on; the output and exit code SHALL be the same from either twin.

#### Scenario: Bad ref
- **WHEN** `la-typecheck --realign-from nosuchref` runs
- **THEN** it exits 2, stderr holds only `typecheck.bad-ref` naming `nosuchref`, and no checker runs

#### Scenario: Combined with write
- **WHEN** `la-typecheck --realign-from HEAD --write-baseline` runs
- **THEN** it exits 2 as a usage error and no baseline changes

#### Scenario: TypeScript repo
- **WHEN** `la-typecheck --realign-from HEAD` runs in a TypeScript-only repo
- **THEN** stdout, stderr and the exit code equal those of `la-typecheck` and the baseline is unchanged

#### Scenario: Mixed repo through either twin
- **WHEN** `la-typecheck --realign-from HEAD` runs through each twin on a mixed repo whose Python baseline needs
  realigning
- **THEN** both runs produce byte-identical stdout, stderr, exit codes and baseline files

### Requirement: Python baseline realignment
For Python, when the baseline file exists, `la-typecheck --realign-from REF` SHALL realign the baseline and then
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
  so both shift by five columns, and `la-typecheck --realign-from HEAD` runs with the edit uncommitted
- **THEN** both entries get the new columns, stderr holds `typecheck.realign` with count 2, and the exit code is 0

#### Scenario: Committed edit
- **WHEN** the same edit is committed and `la-typecheck --realign-from HEAD~1` runs
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
  `la-typecheck --realign-from HEAD` runs
- **THEN** its entries sit under the new path key with the new columns and the exit code is 0

#### Scenario: Renamed file only
- **WHEN** a file with baseline entries is renamed with `git mv` and not edited
- **THEN** its entries sit under the new path key unchanged and the exit code is 0

#### Scenario: Rename onto a key with entries
- **WHEN** the baseline already holds entries under a rename's new path
- **THEN** the key holds both sets of entries in position order

#### Scenario: Nothing to realign
- **WHEN** no baseline-listed file changed since `REF`
- **THEN** stdout, stderr and the exit code equal those of `la-typecheck` and the baseline is byte-identical

#### Scenario: Character outside the BMP before the edit
- **WHEN** a baselined line holds an emoji in a string before the edited text and the error
- **THEN** the entry gets the error's current UTF-16 columns

#### Scenario: Checker fails while realigning
- **WHEN** the configured checker exits 2 on the realignment run
- **THEN** `la-typecheck` exits 2 with the checker-failure text and the baseline is unchanged

#### Scenario: Malformed baseline
- **WHEN** `.basedpyright/baseline.json` is not valid JSON and `la-typecheck --realign-from HEAD` runs
- **THEN** it exits 2 with `typecheck.baseline-invalid` naming `python`

### Requirement: Realignment hint
A Python check without `--realign-from` and without `--write-baseline` that exits 1 while the Python baseline file
exists SHALL print `typecheck.realign-hint` on stderr after the checker's output. No other run SHALL print it.

#### Scenario: New error with a baseline
- **WHEN** `la-typecheck` runs on a Python repo with a baseline file and an error outside it
- **THEN** stderr ends with `typecheck.realign-hint` and the exit code is 1

#### Scenario: New error without a baseline
- **WHEN** `la-typecheck` runs on a Python repo with errors and no baseline file
- **THEN** the hint is not printed

#### Scenario: Failing realign run
- **WHEN** `la-typecheck --realign-from HEAD` exits 1
- **THEN** the hint is not printed
