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

### Requirement: Rename maps apply many renames as one
`dr-refactor rename-map MAP` SHALL read MAP (a path relative to the working directory) as a YAML list of entries
valid against the shared rename-map schema: `file` relative to `--project`, exactly one locator (`symbol`, `line`
with an optional `col`, or `offset`), and exactly one of `new_name` or `retarget` (a `symbol` in the same file). An
invalid map SHALL exit 2 with `refactor.map-invalid` naming every invalid entry's index, in index order, printed by
the invoking twin before any routing; a map that cannot be read or is not a non-empty list SHALL name entry 1. It SHALL
take `rename`'s options other than the locator and `--new-name`, applying to every entry. All entries SHALL be of one
language, else exit 2 with `refactor.map-mixed-languages`; the map runs in that language's twin.

Every locator SHALL be resolved against the code before any entry is computed, so entries name old names. Two
entries resolving to one symbol with the same intent SHALL merge; with different intents they SHALL be refused with
`refactor.map-duplicate` naming both entry indexes, exit 2. Every entry SHALL then be computed on one snapshot of the
project, every rename rule running once over the union of the entries' symbols, with one blind-spot scan for every
member entry's old name and one combined refusal report, sorted as a single rename sorts it. A site any entry
rewrites SHALL NOT be listed as another entry's leftover. Identical edits SHALL merge; every site two entries rewrite
differently SHALL be refused with `refactor.map-conflict` naming the site and both entries, exit 1, writing nothing. Name conflicts SHALL be checked first for each `new_name` entry alone against
the code before the map, in map order, so a swap or a chain of names inside one scope is refused, and then for all
entries' edits together, so entries that meet on one name or capture each other's references are refused. A retarget
entry's rewritten references SHALL resolve to its target, which another entry may rename. A retarget entry whose
target another entry renames SHALL write the target's new name.

`rename` SHALL behave as a one-entry map with a `new_name`, and `retarget` as a one-entry map with a `retarget`;
their output SHALL equal that map's byte for byte.

#### Scenario: Related renames in one pass
- **WHEN** a map renames `StorageBackend.get_model`, `StorageBackend.get_model_sync` and
  `StorageBackend.get_model(model_name)` and runs with `--apply`
- **THEN** stdout has one header line per entry in map order, one diff per changed file and the applied footer, and
  every reference of the three symbols is renamed

#### Scenario: Entries name old names
- **WHEN** a map renames method `A.old` to `new` and, in a later entry, parameter `A.old(x)` to `y`
- **THEN** both renames apply and the method is `new(self, y)`

#### Scenario: One combined refusal
- **WHEN** two member entries each meet one untyped receiver
- **THEN** stderr's final report lists both blind spots in path, line and column order, followed by one
  `refactor.blindspots` line, the exit code is 1 and nothing changes

#### Scenario: Duplicate entries
- **WHEN** two entries locate the same method with new names `a` and `b`
- **THEN** stderr ends with `refactor.map-duplicate` naming both entry indexes and the exit code is 2

#### Scenario: Conflicting edits
- **WHEN** one entry renames `Base.save` to `store` and another renames `Sub.save`, its override, to `keep`
- **THEN** stderr's final report holds `refactor.map-conflict` naming a shared site and both entries, the exit code is
  1 and nothing changes

#### Scenario: Swap in one scope refused
- **WHEN** a map renames parameter `f(x)` to `y` and `f(y)` to `x`
- **THEN** the rename refuses with the existing name-conflict finding of each entry and nothing changes

#### Scenario: Two entries converging on one name
- **WHEN** a map renames parameter `f(x)` to `z` and `f(y)` to `z`
- **THEN** the rename refuses with the existing name-conflict finding and nothing changes

#### Scenario: Two catch variables taking one name
- **WHEN** a TypeScript map renames the variables of two separate `catch` clauses to `err`
- **THEN** both renames apply and the exit code is 0

#### Scenario: Entries capturing each other's references
- **WHEN** one entry renames a module-level `a` to `z`, another renames a function's local `b` to `z`, and that
  function reads `a`, so that each entry alone is clean
- **THEN** the map is refused with the name-conflict finding and nothing changes

#### Scenario: Retarget beside a rename
- **WHEN** a map retargets alias `old_alias` to `target` and renames `target` to `renamed`, and a function reading
  `old_alias` binds no `renamed`
- **THEN** both entries apply and the function reads `renamed`

#### Scenario: Mixed languages
- **WHEN** a map holds a `.py` and a `.ts` entry
- **THEN** stderr is `refactor.map-mixed-languages` and the exit code is 2

#### Scenario: Invalid map
- **WHEN** entry 2 carries both `new_name` and `retarget`
- **THEN** stderr is `refactor.map-invalid` naming entry 2 and the exit code is 2

#### Scenario: Every invalid entry
- **WHEN** entries 2 and 4 are invalid
- **THEN** stderr is `refactor.map-invalid` naming entry 2 and then entry 4, through either invoking twin, and the
  exit code is 2

#### Scenario: Single rename equals its map
- **WHEN** `rename --file F --symbol Q --new-name N` and a map holding that one entry run on the same project
- **THEN** their stdout, stderr and exit codes are identical, through either invoking twin

#### Scenario: Another entry's rewrite is no leftover
- **WHEN** a map renames field `A.columns` to `fields` and `B.columns` to `cols`, and a file passes a
  `{"columns": ...}` dict to each class
- **THEN** each key is rewritten for its own class, no `leftover` line is printed and the exit code is 0
