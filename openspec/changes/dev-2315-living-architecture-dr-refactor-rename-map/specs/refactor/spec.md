## MODIFIED Requirements

### Requirement: dr-refactor --timings prints each phase's wall time
`dr-refactor --timings` SHALL, for every subcommand and after all other output, print on stderr one
`refactor.timing` line per phase whose work ran at least once, in the order of the shared phase list (`load`,
`resolve`, `references`, `rules`, `conflicts`, `blindspot-scan`, `literal-scan`, `literal-probe`, `baseline`,
`write`), then one for `total`. A phase's time SHALL exclude the phases nested in it, and its repeated runs SHALL add
up. The time of the checks made over a run's computed edits (the sites two entries rewrite differently and every
name-conflict check) SHALL count under `conflicts` and under no other phase. The seconds SHALL be the elapsed time
floored to whole centiseconds, never negative, written as whole seconds, a dot and two digits. The lines SHALL be
printed on every exit once the arguments parse: success, a refusal or an error. A run handed to the other language's
twin SHALL print only that twin's lines; a run that exits before any phase ran (a routing or map error, or the other
twin missing) SHALL print only `total`. Without `--timings`, stdout, stderr and the exit code SHALL be unchanged.

#### Scenario: Line format
- **WHEN** a phase took 1.239 seconds and another 0.004 seconds
- **THEN** their lines read `timing: <phase> 1.23s` and `timing: <phase> 0.00s`

#### Scenario: Python Literal rename
- **WHEN** `dr-refactor --timings rename --file m.py --symbol "Kind['a']" --new-name b` runs
- **THEN** stdout is unchanged, and stderr ends with timing lines in list order that include `literal-scan` and
  `literal-probe`, then `total`

#### Scenario: TypeScript rename
- **WHEN** `dr-refactor --timings rename --file src/a.ts --symbol foo --new-name bar` runs
- **THEN** stdout is unchanged, and stderr ends with timing lines in list order, none of them a `literal-` phase,
  then `total`

#### Scenario: Conflict checks timed on their own
- **WHEN** `dr-refactor --timings rename-map map.yaml` runs a map that refuses nothing, in either twin
- **THEN** stderr holds a `conflicts` timing line after the `rules` line and before any `baseline` line

#### Scenario: Refusal still timed
- **WHEN** a member rename with `--timings` refuses on a blind spot
- **THEN** the exit code is 1, and the timing lines follow the refusal on stderr

#### Scenario: Forwarded run
- **WHEN** the npm twin runs `dr-refactor --timings rename --file m.py --symbol f --new-name g`
- **THEN** stderr holds the Python twin's timing lines once, and no line from the npm twin

#### Scenario: Exit before any phase
- **WHEN** `dr-refactor --timings rename-map map.yaml` runs on a map mixing `.py` and `.ts` entries
- **THEN** the map error is printed, then only the `total` timing line, and the exit code is 2

#### Scenario: Option absent
- **WHEN** any `dr-refactor` case of the corpus runs without `--timings`
- **THEN** its output equals its golden

### Requirement: Refactors run in announced phases and report their progress
Every `dr-refactor` subcommand SHALL run in the phases `resolve`, `checks`, `references`, `rules`, `conflicts`,
`baseline` and `write`, in that order, and SHALL print `refactor.progress-phase` on stderr when each phase starts. A
phase that does not run SHALL print nothing: `rules` runs for `rename`, `retarget` and `rename-map` other than a
module rename; `conflicts` runs for `rename`, `retarget` and `rename-map` when the run reaches the checks made over
its computed edits (the sites two entries rewrite differently and every name-conflict check), so not after a
`--fail-fast` stop and not for a module rename whose new name is already taken; `baseline` runs when the refactor's
language has its baseline file at the repo root and, for Python, its `commands.typecheck` entry is set, whether or
not anything is then realigned; `write` runs only with `--apply`.

In `references`, `refactor.progress-item` SHALL be printed for each entry when its reference search starts, in map
order, an entry merged with a duplicate counting once: `n` its position, `count` the number of entries after
merging, `entries` every map index it stands for (`refactor.progress-entry` for one, `refactor.progress-entries` for
several), `new` its new name (a retarget's target name). `move-symbol`, `move-module` and a module rename print no
per-entry lines.

In `rules`, the entries SHALL be taken in groups of one old name, in the order of each group's first entry. When a
group is done, its line SHALL be printed: `refactor.progress-clean` when it has no refusal of its own, else
`refactor.progress-refused` with the number of its refusals, followed by those refusal lines in path, line and column
order. `count` SHALL be the number of groups, `entries` the group's map indexes and `new` its distinct new names in
map order, comma-separated. A group's refusals SHALL be counted after its sites under `--keep` are dropped. Refusals
between entries (map conflicts, name conflicts over the merged edits, unmatched keeps) SHALL appear only in the final
report.

`conflicts` SHALL print its phase line and no per-entry line.

Progress lines SHALL pass through forwarding to the other twin unchanged and in order.

#### Scenario: Phases of a clean map
- **WHEN** `dr-refactor rename-map map.yaml` runs a two-entry map that refuses nothing, without `--apply`, in a repo
  without a baseline file
- **THEN** stderr is `[resolve]`, `[checks]`, `[references]`, one `[references n/2]` line per entry, `[rules]`, one
  `clean` line per old-name group and `[conflicts]`, and stdout is the headers, the diffs and the dry-run footer

#### Scenario: A refused group prints its refusals as it finishes
- **WHEN** a map's second entry meets an untyped receiver and its first does not
- **THEN** the first group's line says `clean`, the second's says `1 refusal(s)` followed by the blind-spot line, and
  the final report lists the blind spot again with the `refactor.blindspots` line, exit code 1

#### Scenario: Unrelated entries sharing an old name
- **WHEN** a map renames two unrelated methods both named `save`, to `store` and `keep`
- **THEN** one `[rules 1/1]` line names `entries 1, 2`, `save -> store, keep`

#### Scenario: Merged duplicate entries
- **WHEN** entries 2 and 5 locate the same symbol with the same new name
- **THEN** one `[references]` line names `entries 2, 5` and `count` is one less than the number of map entries

#### Scenario: Apply phases
- **WHEN** a rename runs with `--apply` in a repo whose Python baseline file exists and checker command is set
- **THEN** stderr holds `[conflicts]`, then `[baseline]` and then `[write]` after `[rules]`

#### Scenario: Name conflict found in its phase
- **WHEN** a rename's new name is already bound where a renamed read resolves
- **THEN** stderr holds `[conflicts]` before the `refactor.name-conflict` finding, and the exit code is 1

#### Scenario: Module rename conflicts
- **WHEN** a Python module rename's edits change what a name means in an importer
- **THEN** stderr is `[resolve]`, `[checks]`, `[references]`, `[conflicts]` and the `refactor.name-conflict` finding,
  with no `[rules]` line

#### Scenario: No conflict phase after a fail-fast stop
- **WHEN** a map runs with `--fail-fast` and its first group refuses
- **THEN** stderr holds no `[conflicts]` line

#### Scenario: Move phases
- **WHEN** `move-module` runs without `--apply`
- **THEN** stderr is `[resolve]`, `[checks]`, `[references]` and no per-entry line

#### Scenario: Progress through the other twin
- **WHEN** a TypeScript rename runs through the PyPI twin
- **THEN** stdout, stderr and exit code equal the npm twin's own run
