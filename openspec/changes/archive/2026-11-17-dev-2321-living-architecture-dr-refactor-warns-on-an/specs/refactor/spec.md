## MODIFIED Requirements

### Requirement: Member renames refuse on unclassified stand-ins
The renamed hierarchy SHALL be every declaration the rename renames with hierarchy on (Python: every member
declaration of OLD whose roots meet the located declaration's roots, where the roots of a declaration in class `C`
are the roots of OLD's declaration in each direct base of `C` that has OLD as the checker resolves it, or the
declaration itself when no direct base has OLD; TypeScript: the declarations
the language service's rename returns, merged interface declarations included), whether or not `--no-in-hierarchy` is
given, joined with the hierarchy of every `--with` stand-in. A stand-in SHALL be a class (Python) or a class,
interface or type literal (TypeScript), declared in a project source file of the rename's language and outside the
renamed hierarchy, that declares a member named OLD. Object literals SHALL NOT be stand-ins.

A member rename with any stand-in that is neither `--with` nor `--without` SHALL print one `refactor.stand-in` line
per stand-in member declaration on stderr, sorted by path, line and column and after any blind-spot lines, print
nothing on stdout, write nothing and exit 1, with or without `--apply`.

`--with PATH:LINE` and `--without PATH:LINE` (each repeatable) SHALL classify every stand-in member declared on that
line, together with that stand-in's own hierarchy. A `--with` stand-in SHALL be renamed in the same run: its
hierarchy joins the renamed hierarchy, and every rule of the rename (references, keyed rewrites, string-member
forms, `--docs`, `--keep`, blind spots) SHALL run once over the joined set, on one snapshot of the files, identical
edits merged. A `--without` stand-in SHALL be unchanged. A `--with` or `--without` naming no existing file or line
SHALL print `refactor.site-missing` in the `checks` phase. One whose line holds no stand-in member declaration of this
rename SHALL print `refactor.not-stand-in` at site resolution, which stops the run: nothing is written and the exit
code is 2. A Python module rename has no stand-ins: each of its `--with` and `--without` sites SHALL print
`refactor.not-stand-in` in the `checks` phase.
A TypeScript stand-in member declared by a computed name SHALL be classified by `--without` like any other;
`--with` naming its line SHALL print `refactor.computed-stand-in` at site resolution, write nothing and exit 2.

#### Scenario: Cast stand-in refuses until classified
- **WHEN** `StorageBackend.get_model` is renamed and `class _ModelReadCache` (no base in the hierarchy) defines
  `get_model` and is used as `cast(StorageBackend, _ModelReadCache(...))`
- **THEN** stderr's final report is the `refactor.stand-in` line naming `_ModelReadCache.get_model` with its path and
  line, the exit code is 1 and no file changes

#### Scenario: --with renames the stand-in in the same diff
- **WHEN** the same rename runs with `--with <that path>:<that line>`, and a module calls `c.get_model()` with
  `c: _ModelReadCache`
- **THEN** the diff renames both hierarchies' declarations and every call through either, and the exit code is 0

#### Scenario: --without leaves an unrelated class
- **WHEN** `class Unrelated` also defines `get_model` and the rename passes `--without` its line
- **THEN** `Unrelated.get_model` and calls through `u: Unrelated` are unchanged

#### Scenario: Shared references across several --with stand-ins
- **WHEN** two stand-ins are passed with `--with` and a `--docs` mention and a call site are reached through both
- **THEN** each site is rewritten once and the exit code is 0

#### Scenario: Classification line without a stand-in
- **WHEN** `--with` names an existing line that declares no stand-in member of this rename
- **THEN** stderr holds the `[rules]` lines and no `[conflicts]` line, the final report holds `refactor.not-stand-in`
  naming that site, the exit code is 2 and no file changes

#### Scenario: Classification site on a Python module rename
- **WHEN** a Python module rename passes `--with pkg/use.py:3`
- **THEN** stderr is `[resolve]`, `[checks]` and `refactor.not-stand-in` naming `pkg/use.py:3`, no `[references]`
  line is printed, the exit code is 2 and no file changes

#### Scenario: Two stand-ins on one line
- **WHEN** one line declares two stand-in members named OLD and `--without` names that line
- **THEN** both are classified and neither is reported

#### Scenario: Hierarchy flag off
- **WHEN** `A.run` is renamed with `--no-in-hierarchy` and `B(A)` overrides `run`
- **THEN** `B` is not reported as a stand-in

#### Scenario: Python diamond and mixin hierarchy
- **WHEN** `A.run` is renamed, `B(A)` and `C(A)` override `run`, `D(B, C)` overrides it, and an unrelated mixin
  `M` declaring `run` is a base of `E(M, A)`
- **THEN** `A.run`, `B.run`, `C.run` and `D.run` are renamed, and `M.run` is reported as a stand-in

#### Scenario: TypeScript structural class and object literal
- **WHEN** interface `Store.getModel` is renamed, `class Fake { getModel() {} }` does not implement `Store`, and an
  untyped constant holds `{ getModel() {} }`
- **THEN** `Fake.getModel` is reported as a stand-in and the object literal is not

#### Scenario: Computed-name stand-in
- **WHEN** interface `Store.getModel` is renamed and `class Keyed { [KEY]() {} }` declares it through
  `const KEY = 'getModel'`
- **THEN** `Keyed.getModel` is reported as a stand-in; `--without` its line classifies it, and `--with` its line
  prints `refactor.computed-stand-in` at site resolution, writes nothing and exits 2

### Requirement: --keep leaves sites untouched
`dr-refactor rename` SHALL accept `--keep PATH[:LINE]` (repeatable). PATH SHALL be resolved against the working
directory to a real path under the project; a directory SHALL match the files under it by whole path components.
Every edit the rename would make on a kept line, in a kept file or under a kept directory SHALL be dropped,
whichever rule produced it, and a blind spot there SHALL NOT block the rename. A `--keep` naming no existing file,
directory or line SHALL print `refactor.site-missing` in the `checks` phase, and a line keep whose line holds no old
name SHALL print `refactor.keep-unmatched` there (see the cheap checks).

At site resolution, a keep that matched no edit and no blind spot SHALL be decided by its form:
- a whole-file or directory keep (no `:LINE`) leaves the outcome as asked: it SHALL print `refactor.keep-unneeded`
  naming it on stderr, and the run SHALL go on and, with `--apply`, write;
- a line keep SHALL be refused, with `refactor.keep-unmatched-near` naming the edited line of its file nearest to the
  kept line, else `refactor.keep-unmatched` when its file holds no edited line. An edited line is the start line of
  an edit the run writes, after every keep is applied; of two edited lines equally near, the earlier SHALL be named.
  Every such keep SHALL be reported, nothing SHALL be written and the exit code SHALL be 2.

Keeping a declaration SHALL NOT keep its references.

#### Scenario: Back-compat line kept
- **WHEN** `Storage.get_model` is renamed with `--keep tests/test_compat.py:12`, where line 12 calls
  `storage.get_model("m")`
- **THEN** line 12 is unchanged and every other reference is renamed

#### Scenario: Kept file and directory
- **WHEN** the rename passes `--keep tests/compat` and `--keep tests/test_shim.py`
- **THEN** no file under `tests/compat/` or `tests/test_shim.py` changes, while `tests/compatible.py` is renamed

#### Scenario: File keep and line keep together
- **WHEN** the rename passes both `--keep a.py` and `--keep a.py:3`
- **THEN** `a.py` is unchanged and the exit code is 0

#### Scenario: Unneeded file keep
- **WHEN** a rename runs with `--apply` and `--keep src/compat.py`, a file spelling the old name where no edit and no
  blind spot of the rename lands
- **THEN** stderr holds `refactor.keep-unneeded` naming `src/compat.py` after the last `[rules]` line and before
  `[conflicts]`, the rename is written and the exit code is 0

#### Scenario: Unneeded directory keep
- **WHEN** a rename runs with `--apply` and `--keep tests/compat`, a directory whose files hold no edit and no blind
  spot of the rename
- **THEN** stderr holds `refactor.keep-unneeded` naming `tests/compat`, the rename is written and the exit code is 0

#### Scenario: Unmatched keep
- **WHEN** `--keep src/a.py:9` names a code line spelling the old name where no edit of the rename lands, and the
  rename edits `src/a.py` on lines 4 and 12
- **THEN** stderr holds no `[conflicts]` line and ends with `refactor.keep-unmatched-near` naming `src/a.py:9` and
  line 12, the exit code is 2 and no file changes

#### Scenario: Unmatched line keep in a file without edits
- **WHEN** `--keep src/b.py:3` names a code line spelling the old name, and the rename edits nothing in `src/b.py`
- **THEN** stderr ends with `refactor.keep-unmatched` naming `src/b.py:3`, the exit code is 2 and no file changes

#### Scenario: Kept module file
- **WHEN** a Python module `pkg/old.py` is renamed with `--keep pkg/old.py`
- **THEN** the checks pass, the module is not moved and no `refactor.keep-unneeded` is printed

#### Scenario: Kept moved package
- **WHEN** a Python package `pkg/old/` is renamed with `--keep pkg/old`
- **THEN** the package is not moved, no `refactor.keep-unneeded` is printed and the exit code is 0

### Requirement: Refactors run in announced phases and report their progress
Every `dr-refactor` subcommand SHALL run in the phases `resolve`, `checks`, `references`, `rules`, `conflicts`,
`baseline` and `write`, in that order, and SHALL print `refactor.progress-phase` on stderr when each phase starts. A
phase that does not run SHALL print nothing: `rules` runs for `rename`, `retarget` and `rename-map` other than a
module rename; `conflicts` runs for `rename`, `retarget` and `rename-map` when the run reaches the checks made over
its computed edits (the sites two entries rewrite differently and every name-conflict check), so not after a
`--fail-fast` stop, not after a refusing finding at site resolution and not for a module rename whose new name is
already taken; `baseline` runs when the refactor's language has its baseline file at the repo root and, for Python,
its `commands.typecheck` entry is set, whether or not anything is then realigned; `write` runs only with `--apply`.

Site resolution SHALL run once every entry's edits are final (every group's rules done, the imports retargets need
planned and every keep applied; for a module rename, once its edits and moves are filtered by the keeps) and before
`conflicts`. It prints no phase line; its `refactor.keep-unneeded` lines SHALL be printed there, in command-line
order.

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
between entries (map conflicts, name conflicts over the merged edits, site findings) SHALL appear only in the final
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

#### Scenario: No conflict phase after a refusing site finding
- **WHEN** a map runs without `--fail-fast` and a line keep matches nothing
- **THEN** stderr holds every `[rules]` result line, no `[conflicts]` line and then the final report

#### Scenario: Warnings before the conflict phase
- **WHEN** a map runs with an unneeded file keep and nothing refuses
- **THEN** stderr holds the `[rules]` result lines, then `refactor.keep-unneeded`, then `[conflicts]`

#### Scenario: Move phases
- **WHEN** `move-module` runs without `--apply`
- **THEN** stderr is `[resolve]`, `[checks]`, `[references]` and no per-entry line

#### Scenario: Progress through the other twin
- **WHEN** a TypeScript rename runs through the PyPI twin
- **THEN** stdout, stderr and exit code equal the npm twin's own run

### Requirement: Cheap checks run before any reference search
Resolving every entry's locator SHALL search no references. Every resolution failure SHALL be collected with its entry
index, not stop the run: unresolved or ambiguous symbol paths, an out-of-range line, column or offset, a location that
cannot be renamed, a retarget out of scope, a literal value that cannot be written, a TypeScript file outside every
project. Duplicate entries SHALL be found among the resolved entries only.

The `checks` phase SHALL then run, before any reference search:
- every `--keep`, `--with` and `--without` SHALL name an existing file or directory under the project, and a `:LINE`
  a line of an existing file, else `refactor.site-missing` naming the option and the site;
- every line keep (`--keep PATH:LINE`) SHALL name a line, in a file the run can edit (a source of its language, and
  with `--docs` a prose file), whose text holds an entry's old name or a retarget entry's target name, either as
  written (with identifier escapes decoded, and NFKC-normalized for Python) or in the value of a string literal
  starting on that line; or lie in a file the refactor moves; else `refactor.keep-unmatched`. Without `--docs`, a
  spelling inside a comment SHALL NOT count, except in a Python type comment (a comment whose text after `#` and
  optional whitespace starts with `type:`). When an entry that did not resolve spells no name in its locator, or an
  entry renames a `Literal` member, this check SHALL be skipped. A whole-file or directory keep SHALL get no check
  here beyond the site check;
- a Python module rename SHALL refuse each `--with` and `--without` site with `refactor.not-stand-in`;
- Python: every module rope walks before the reference search SHALL be walked as `dr-compliance --select rope-walk`
  walks it, and each gap reported as `refactor.rope-walk`: for a move or a module rename every candidate file (a Python
  source whose text holds the moved name or module's name), for any other entry the module locating it;
- Python: the language server SHALL start for `rename`, `retarget` and `rename-map` unless an entry renames a module,
  or the run's occurrence index is cached and no entry renames a `Literal` member, and when the baseline phase will run, the configured checker SHALL run once on one source of the refactor; a failure SHALL be reported with its
  cause;
- in both twins, when the refactor's language has its baseline file at the repo root, the repo config SHALL be
  readable and valid, else its error SHALL be reported as the config loader words it, exit 2.

Each `--keep`, `--with` and `--without` argument SHALL get at most one finding; a failure in `checks` SHALL replace its
later exact check. When `resolve` or `checks` found anything, the run SHALL print nothing on stdout, print every
finding on stderr (resolution findings by entry index, site findings in command-line order, walker gaps by path, then
checker findings), print no `[references]` line, write nothing, and exit with the highest exit code of its findings.

#### Scenario: Missing keep path
- **WHEN** a rename passes `--keep src/gone.py`
- **THEN** stderr is `[resolve]`, `[checks]` and `refactor.site-missing` naming `--keep src/gone.py`, the exit code is
  2 and no file changes

#### Scenario: Keep line past the end
- **WHEN** `--keep src/a.py:99` names a line past the end of a 20-line file
- **THEN** stderr ends with `refactor.site-missing` naming `--keep src/a.py:99` and the exit code is 2

#### Scenario: Keep holding no old name
- **WHEN** `--keep architecture` names a directory whose files never spell the renamed name
- **THEN** the checks pass, `refactor.keep-unneeded` naming it is printed at site resolution and the exit code is 0

#### Scenario: Every bad keep at once
- **WHEN** a rename passes three keeps, one missing and two line keeps whose lines hold no old name
- **THEN** stderr lists all three findings in command-line order and the exit code is 2

#### Scenario: Comment-only line keep without --docs
- **WHEN** `--keep src/a.py:9` names a line whose only spelling of the old name is in a comment (a trailing comment
  or a line of a multi-line comment), without `--docs`
- **THEN** stderr ends with `refactor.keep-unmatched` naming `src/a.py:9`, no `[references]` line is printed and the
  exit code is 2

#### Scenario: Comment-only line keep with --docs
- **WHEN** the same keep runs with `--docs` and `--apply`, and the rename's `--docs` pass rewrites mentions of the old
  name in comments
- **THEN** the checks pass, every other mention is rewritten, line 9 is unchanged and the exit code is 0

#### Scenario: Python type comment counts as code
- **WHEN** `--keep src/a.py:4` names a line whose only spelling of the old name is in `# type: Old`, without `--docs`
- **THEN** the check passes and the run goes on to `references`

#### Scenario: Missing classification site
- **WHEN** a member rename passes `--with src/gone.py:3` and `--without src/a.py:400`
- **THEN** stderr lists `refactor.site-missing` for both, no `[references]` line is printed and the exit code is 2

#### Scenario: Unresolved entries listed together
- **WHEN** map entries 2 and 4 name symbols their files do not declare
- **THEN** stderr lists `refactor.symbol-unresolved` for entry 2 and then for entry 4, and the exit code is 2

#### Scenario: Unresolved entry and bad keep
- **WHEN** entry 1 does not resolve and `--keep src/gone.py` is passed
- **THEN** stderr lists the entry's finding and then `refactor.site-missing`, and the exit code is 2

#### Scenario: Keep matched by an escaped spelling
- **WHEN** `--keep src/a.py:7` names a line whose only spelling of the old name is an escaped string literal
- **THEN** the check passes and the run goes on to `references`

#### Scenario: Keep on a retarget's import line
- **WHEN** a TypeScript retarget passes `--keep` on an import of the target that the retarget removes as a duplicate
- **THEN** the check passes and the import line is unchanged

#### Scenario: Keep of a prose file needs --docs
- **WHEN** `--keep README.md:3` names a line of a prose file that mentions the old name
- **THEN** the check passes with `--docs`, and without it stderr is `refactor.keep-unmatched` naming it

#### Scenario: Walker gaps listed before any search
- **WHEN** rope's walker cannot cover `pkg/a.py` at line 3 nor `pkg/b.py` at line 8, and each is the module locating
  an entry of the map
- **THEN** stderr lists `refactor.rope-walk` for both files in path order, no `[references]` line is printed, the
  exit code is 1 and no file changes

#### Scenario: Checker that cannot run
- **WHEN** `commands.typecheck.python` names a command that exits 2 with a message on stderr, and the baseline file
  exists
- **THEN** stderr ends with `refactor.baseline-failed` and its cause, no `[references]` line is printed and the exit
  code is 1

#### Scenario: Unreadable config
- **WHEN** a rename runs where the language's baseline file exists and `living-architecture.yaml` is not valid YAML
- **THEN** stderr ends with the config error, no `[references]` line is printed, the exit code is 2 and no file
  changes

### Requirement: Every refusal of a run is reported in one report
A run SHALL refuse once, with every refusal it found: those of `resolve` and `checks` as one report before any
reference search, else every refusal found while computing the entries. A walker gap the checks did not predict and
an unresolved base SHALL be recorded and the run SHALL go on. Once every entry's edits are final, site resolution
SHALL decide every `--keep`, `--with` and `--without` site exactly (see the `--keep` and stand-in requirements); it
SHALL be skipped after a `--fail-fast` stop and, in the Python twin, when an entry failed while computing. When it
finds a refusing site finding, the run SHALL stop there, before `conflicts`, and report. Otherwise, after
`conflicts`, every site two entries rewrite differently and the finding of every name-conflict check that finds one
(each distinct finding once) SHALL be reported. The final report SHALL be: retarget refusals, blind spots, stand-ins,
name conflicts and map conflicts, each group in path, line and column order; then the site findings
(`refactor.not-stand-in` for the `--with` and then the `--without` sites, then `refactor.computed-stand-in`, then
the keep findings, each in command-line order); then the `refactor.blindspots` line when blind spots refuse. Its
exit code SHALL be the highest of its findings', 2 for an invalid or duplicate map entry (`refactor.map-invalid`,
`refactor.map-duplicate`), a locator or a site finding, and 1 otherwise, `refactor.map-conflict` included. A file
that changed while the run read it, a write that failed, a checker that failed while computing, and a map document
that cannot be read SHALL still stop the run at once.

#### Scenario: Retarget refusal and blind spot together
- **WHEN** a map's retarget entry meets an overriding member and its rename entry meets an untyped receiver
- **THEN** stderr's final report lists the retarget refusal and then the blind spot with the `refactor.blindspots`
  line, and the exit code is 1

#### Scenario: Late unmatched keep with other refusals
- **WHEN** `--keep src/a.py:5` names a code line spelling the old name where no edit lands, and an entry meets an
  untyped receiver
- **THEN** stderr holds no `[conflicts]` line, the final report lists the blind spot, then the keep finding naming
  `src/a.py:5`, then the `refactor.blindspots` line, and the exit code is 2

#### Scenario: Unneeded keep and unmatched line keep together
- **WHEN** a rename passes an unneeded `--keep src/compat.py` and a line keep `--keep src/a.py:5` that matches nothing
- **THEN** stderr holds `refactor.keep-unneeded` naming `src/compat.py`, then the final report with the line keep's
  finding, no `[conflicts]` line, and the exit code is 2

#### Scenario: Unneeded keep with a blind spot
- **WHEN** a rename passes an unneeded `--keep src/compat.py` and an entry meets an untyped receiver
- **THEN** stderr holds `refactor.keep-unneeded`, then `[conflicts]`, then the final report with the blind spot, and
  the exit code is 1

#### Scenario: Two map conflicts
- **WHEN** two pairs of entries each rewrite one site differently
- **THEN** stderr lists `refactor.map-conflict` for both sites in path order and the exit code is 1

### Requirement: --fail-fast stops at the first refusal
`dr-refactor rename`, `retarget` and `rename-map` SHALL accept `--fail-fast`. With it, the run SHALL stop at the first
refusal found after `checks`: the entry or group in progress SHALL finish its phase and print its line, no later one
SHALL start that phase and no later phase SHALL run. The final report SHALL list what was found, without site
resolution (no exact site finding and no `refactor.keep-unneeded`). Without it, every entry SHALL be computed and
every refusal reported, up to a stop at site resolution.

#### Scenario: Stop after the first refused group
- **WHEN** a three-entry map with distinct old names runs with `--fail-fast` and its first entry meets an untyped
  receiver
- **THEN** stderr holds one `[rules 1/3]` refused line and no `[rules 2/3]` line, the final report lists that blind
  spot, and the exit code is 1

#### Scenario: Default computes every entry
- **WHEN** the same map runs without `--fail-fast` and its first and third entries each meet an untyped receiver
- **THEN** stderr holds three `[rules]` result lines and the final report lists both blind spots
