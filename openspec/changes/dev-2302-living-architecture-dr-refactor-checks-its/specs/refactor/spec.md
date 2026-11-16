## ADDED Requirements

### Requirement: Refactors run in announced phases and report their progress
Every `dr-refactor` subcommand SHALL run in the phases `resolve`, `checks`, `references`, `rules`, `baseline` and
`write`, in that order, and SHALL print `refactor.progress-phase` on stderr when each phase starts. A phase that does
not run SHALL print nothing: `rules` runs for `rename`, `retarget` and `rename-map` other than a module rename;
`baseline` runs when the refactor's language has its baseline file at the repo root and, for Python, its
`commands.typecheck` entry is set, whether or not anything is then realigned; `write` runs only with `--apply`.

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

Progress lines SHALL pass through forwarding to the other twin unchanged and in order.

#### Scenario: Phases of a clean map
- **WHEN** `dr-refactor rename-map map.yaml` runs a two-entry map that refuses nothing, without `--apply`, in a repo
  without a baseline file
- **THEN** stderr is `[resolve]`, `[checks]`, `[references]`, one `[references n/2]` line per entry, `[rules]` and one
  `clean` line per old-name group, and stdout is the headers, the diffs and the dry-run footer

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
- **THEN** stderr holds `[baseline]` and then `[write]` after `[rules]`

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
- every `--keep` SHALL cover at least one line, in a file the run can edit (a source of its language, and with `--docs`
  a prose file), whose text holds an entry's old name or a retarget entry's target name, either as written (with
  identifier escapes decoded, and NFKC-normalized for Python) or in the value of a string literal starting on that
  line; or cover a file the refactor moves; else `refactor.keep-unmatched`. When an entry that did not resolve spells
  no name in its locator, or an entry renames a `Literal` member, this check SHALL be skipped;
- Python: every candidate file (a Python source whose text holds an entry's old name, or the moved name or module's
  name) SHALL be walked as `dr-compliance --select rope-walk` walks it, and each gap reported as `refactor.rope-walk`;
- Python: the language server SHALL start for `rename`, `retarget` and `rename-map`, and when the baseline phase will
  run, the configured checker SHALL run once on one source of the refactor; a failure SHALL be reported with its
  cause.

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
- **THEN** stderr ends with `refactor.keep-unmatched` naming it, no `[references]` line is printed and the exit code
  is 2

#### Scenario: Every bad keep at once
- **WHEN** a rename passes three keeps, one missing and two holding no old name
- **THEN** stderr lists all three findings in command-line order and the exit code is 2

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
- **WHEN** `--keep README.md` names a prose file that mentions the old name
- **THEN** the check passes with `--docs`, and without it stderr is `refactor.keep-unmatched` naming it

#### Scenario: Walker gaps listed before any search
- **WHEN** rope's walker cannot cover `pkg/a.py` at line 3 nor `pkg/b.py` at line 8, and both spell the old name
- **THEN** stderr lists `refactor.rope-walk` for both files in path order, no `[references]` line is printed, the
  exit code is 1 and no file changes

#### Scenario: Checker that cannot run
- **WHEN** `commands.typecheck.python` names a command that exits 2 with a message on stderr, and the baseline file
  exists
- **THEN** stderr ends with `refactor.baseline-failed` and its cause, no `[references]` line is printed and the exit
  code is 1

### Requirement: Every refusal of a run is reported in one report
A run SHALL refuse once, with every refusal it found: those of `resolve` and `checks` as one report before any
reference search, else every refusal found while computing the entries. A walker gap the checks did not predict, an
unresolved base and a site that classifies no stand-in SHALL be recorded and the run SHALL go on. After the rules:
every `--keep` that matched no edit and no blind spot, every site two entries rewrite differently, and the finding of
every name-conflict check that finds one (each distinct finding once) SHALL be reported. The final report SHALL be:
retarget refusals, blind spots, stand-ins, name conflicts and map conflicts, each group in path, line and column
order; then the site findings in command-line order; then the `refactor.blindspots` line when blind spots refuse. Its
exit code SHALL be the highest of its findings', 2 for an invalid or duplicate map entry (`refactor.map-invalid`,
`refactor.map-duplicate`), a locator or a site finding, and 1 otherwise, `refactor.map-conflict` included. A file
that changed while the run read it, a write that failed, a checker that failed while computing, and a map document
that cannot be read SHALL still stop the run at once.

#### Scenario: Retarget refusal and blind spot together
- **WHEN** a map's retarget entry meets an overriding member and its rename entry meets an untyped receiver
- **THEN** stderr's final report lists the retarget refusal and then the blind spot with the `refactor.blindspots`
  line, and the exit code is 1

#### Scenario: Late unmatched keep with other refusals
- **WHEN** `--keep src/a.py:5` names a comment line spelling the old name, without `--docs`, and an entry meets an
  untyped receiver
- **THEN** the final report lists the blind spot, then `refactor.keep-unmatched` naming `src/a.py:5`, then the
  `refactor.blindspots` line, and the exit code is 2

#### Scenario: Two map conflicts
- **WHEN** two pairs of entries each rewrite one site differently
- **THEN** stderr lists `refactor.map-conflict` for both sites in path order and the exit code is 1

### Requirement: --fail-fast stops at the first refusal
`dr-refactor rename`, `retarget` and `rename-map` SHALL accept `--fail-fast`. With it, the run SHALL stop at the first
refusal found after `checks`: the entry or group in progress SHALL finish its phase and print its line, no later one
SHALL start that phase and no later phase SHALL run. The final report SHALL list what was found, without the exact
check of `--keep`. Without it, every entry SHALL be computed and every refusal reported.

#### Scenario: Stop after the first refused group
- **WHEN** a three-entry map with distinct old names runs with `--fail-fast` and its first entry meets an untyped
  receiver
- **THEN** stderr holds one `[rules 1/3]` refused line and no `[rules 2/3]` line, the final report lists that blind
  spot, and the exit code is 1

#### Scenario: Default computes every entry
- **WHEN** the same map runs without `--fail-fast` and its first and third entries each meet an untyped receiver
- **THEN** stderr holds three `[rules]` result lines and the final report lists both blind spots

### Requirement: A failed checker's cause is printed
When the Python language server or the configured Python checker fails, its finding (`refactor.pyright-failed` or
`refactor.baseline-failed`) SHALL be followed by its cause: `refactor.checker-exit` with its exit code and then its
stderr lines, each indented by two spaces; `refactor.checker-not-started` with the error when it could not start; or
`refactor.checker-error` with its error answer, then any stderr captured. A baseline file that cannot be read SHALL
print `refactor.baseline-failed` with no cause.

#### Scenario: Language server that cannot start
- **WHEN** the language server's command does not exist
- **THEN** stderr ends with `refactor.pyright-failed` and `refactor.checker-not-started`, and the exit code is 1

#### Scenario: Checker failing during alignment
- **WHEN** the configured checker passes the probe and exits 2 with a message while realigning the baseline
- **THEN** stderr ends with `refactor.baseline-failed`, `refactor.checker-exit` naming exit code 2 and the message
  indented by two spaces, the exit code is 1 and nothing is written

## MODIFIED Requirements

### Requirement: Refactor output format
`dr-refactor` SHALL print one header line per refactor entry in order (a rename map's entries in map order, entries
merged as duplicates counting once), then one unified diff per changed file sorted by path (`--- a/<path>`,
`+++ b/<path>`, three context lines, no end-of-file marker), the type-check baseline included, a `rename from` /
`rename to` pair for every moved file, then the dry-run or applied footer. Progress, refusals, leftovers and warnings
SHALL be printed on stderr. Every header, footer, progress line, warning and error SHALL come from the findings
registry; no checker or library message text SHALL be printed, except a failed checker's cause after its finding. The
diff format SHALL be pinned by shared vectors that both twins pass, covering a missing final newline, CRLF line
endings, created and deleted files, and paths with spaces or non-ASCII characters.

#### Scenario: TS rename dry-run
- **WHEN** `dr-refactor rename --file src/a.ts --symbol foo --new-name bar` runs on a project where `src/b.ts` imports `foo`
- **THEN** stdout is the rename header, the diffs of `src/a.ts` and `src/b.ts` in path order, and the dry-run footer naming 2 files, and no file changes

#### Scenario: Map headers
- **WHEN** a map holds a rename entry and then a retarget entry
- **THEN** stdout starts with the rename header line and then the retarget header line

#### Scenario: Merged entries share a header
- **WHEN** entries 1 and 2 locate the same symbol with the same new name
- **THEN** stdout holds one header line for them

#### Scenario: Diff vectors
- **WHEN** either twin's suite runs
- **THEN** its diff formatter reproduces every shared diff vector byte for byte

### Requirement: A Python walker gap is refused with a located finding
When rope's walker fails on a module while the Python `dr-refactor` computes a refactor, or leaves part of it
uncovered, `dr-refactor` SHALL refuse with the `refactor.rope-walk` finding on stderr, naming the file and the line
of the construct, and exit 1. Every gap in a candidate file SHALL be found in the `checks` phase, before any reference
search, and all of them reported together; a gap met later SHALL refuse the entry that met it while the run goes on.
It SHALL write no file, with or without `--apply`, and print no rope or library message text. The line SHALL be:
- the start line of the first uncovered syntax node or string literal in source order;
- else the start line of the first top-level statement the walker cannot cover on its own;
- else 1.

A gap that does not crash SHALL be refused like one that does. Any other failure SHALL NOT be reported as a
walker gap.

#### Scenario: Gap reported at the construct, not at the drift
- **WHEN** the walker leaves a parameter annotation on line 3 uncovered and its token search fails on line 9
- **THEN** stderr ends with `refactor.rope-walk` naming the module and line 3, the exit code is 1 and no file changes

#### Scenario: Apply writes nothing on a gap
- **WHEN** `dr-refactor --apply rename …` hits a walker gap in any module it analyses
- **THEN** it exits 1 with `refactor.rope-walk` and every file of the project is unchanged

#### Scenario: Silent gap refused
- **WHEN** the walker finishes a module without error but leaves a string literal's tail uncovered
- **THEN** `dr-refactor` exits 1 with `refactor.rope-walk` naming that literal's line

### Requirement: --keep leaves sites untouched
`dr-refactor rename` SHALL accept `--keep PATH[:LINE]` (repeatable). PATH SHALL be resolved against the working
directory to a real path under the project; a directory SHALL match the files under it by whole path components.
Every edit the rename would make on a kept line, in a kept file or under a kept directory SHALL be dropped,
whichever rule produced it, and a blind spot there SHALL NOT block the rename. A `--keep` naming no existing file,
directory or line SHALL print `refactor.site-missing`, and one whose sites hold no old name SHALL print
`refactor.keep-unmatched`, both in the `checks` phase. A `--keep` that passes the checks but matches no edit and no
blind spot SHALL print `refactor.keep-unmatched` naming it in the final report. Every such keep SHALL be reported,
nothing SHALL be written and the exit code SHALL be 2. Keeping a declaration SHALL NOT keep its references.

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

#### Scenario: Unmatched keep
- **WHEN** `--keep src/a.py:9` names a line spelling the old name in a comment, without `--docs`
- **THEN** stderr ends with `refactor.keep-unmatched` naming `src/a.py:9`, the exit code is 2 and no file changes

#### Scenario: Kept module file
- **WHEN** a Python module `pkg/old.py` is renamed with `--keep pkg/old.py`
- **THEN** the checks pass and the module is not moved

### Requirement: Member renames refuse on unclassified stand-ins
The renamed hierarchy SHALL be every declaration the rename renames with hierarchy on (Python: rope's hierarchy;
TypeScript: the declarations the language service's rename returns, merged interface declarations included),
whether or not `--no-in-hierarchy` is given, joined with the hierarchy of every `--with` stand-in. A stand-in SHALL
be a class (Python) or a class, interface or type literal (TypeScript), declared in a project source file of the
rename's language and outside the renamed hierarchy, that declares a member named OLD. Object literals SHALL NOT be
stand-ins.

A member rename with any stand-in that is neither `--with` nor `--without` SHALL print one `refactor.stand-in` line
per stand-in member declaration on stderr, sorted by path, line and column and after any blind-spot lines, print
nothing on stdout, write nothing and exit 1, with or without `--apply`.

`--with PATH:LINE` and `--without PATH:LINE` (each repeatable) SHALL classify every stand-in member declared on that
line, together with that stand-in's own hierarchy. A `--with` stand-in SHALL be renamed in the same run: its
hierarchy joins the renamed hierarchy, and every rule of the rename (references, keyed rewrites, string-member
forms, `--docs`, `--keep`, blind spots) SHALL run once over the joined set, on one snapshot of the files, identical
edits merged. A `--without` stand-in SHALL be unchanged. A `--with` or `--without` naming no existing file or line
SHALL print `refactor.site-missing` in the `checks` phase. One whose line holds no stand-in member declaration of this
rename SHALL print `refactor.not-stand-in` on stderr in the final report, write nothing and exit 2.
A TypeScript stand-in member declared by a computed name SHALL be classified by `--without` like any other;
`--with` naming its line SHALL print `refactor.computed-stand-in` on stderr, write nothing and exit 2.

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
- **THEN** stderr's final report holds `refactor.not-stand-in` naming that site, the exit code is 2 and no file changes

#### Scenario: Two stand-ins on one line
- **WHEN** one line declares two stand-in members named OLD and `--without` names that line
- **THEN** both are classified and neither is reported

#### Scenario: Hierarchy flag off
- **WHEN** `A.run` is renamed with `--no-in-hierarchy` and `B(A)` overrides `run`
- **THEN** `B` is not reported as a stand-in

#### Scenario: TypeScript structural class and object literal
- **WHEN** interface `Store.getModel` is renamed, `class Fake { getModel() {} }` does not implement `Store`, and an
  untyped constant holds `{ getModel() {} }`
- **THEN** `Fake.getModel` is reported as a stand-in and the object literal is not

#### Scenario: Computed-name stand-in
- **WHEN** interface `Store.getModel` is renamed and `class Keyed { [KEY]() {} }` declares it through
  `const KEY = 'getModel'`
- **THEN** `Keyed.getModel` is reported as a stand-in; `--without` its line classifies it, and `--with` its line
  prints `refactor.computed-stand-in`, writes nothing and exits 2

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
member entry's old name and one combined refusal report, sorted as a single rename sorts it. Identical edits SHALL
merge; every site two entries rewrite differently SHALL be refused with `refactor.map-conflict` naming the site and
both entries, exit 1, writing nothing. Name conflicts SHALL be checked first for each `new_name` entry alone against
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
  the edits applied in memory, keyed as `la-typecheck` keys tsc's output. A baselined key whose instances all map to
  one new key SHALL move its count there.

A diagnostic whose range cannot be mapped, or a TypeScript key whose instances map to different keys while only
some are baselined, SHALL leave its entry unchanged and print `refactor.baseline-ambiguous` on stderr, without
changing the exit code. A checker run that fails SHALL exit 1 with `refactor.baseline-failed` naming the language,
followed by the checker's cause, and write nothing.

#### Scenario: Rename shifts baselined columns
- **WHEN** a line holds a baselined `reportArgumentType` error after a call of `get_model`, and `get_model` is
  renamed to `load` with `--apply`
- **THEN** that entry's columns shift by the length difference, every other entry is unchanged, and `la-typecheck`
  passes afterwards

#### Scenario: Dry-run shows the baseline
- **WHEN** the same rename runs without `--apply`
- **THEN** the diff of `.basedpyright/baseline.json` is printed with the source diffs and nothing is written

#### Scenario: Matching follows basedpyright
- **WHEN** a file's baseline holds two identical-shaped entries, a stale entry, and an entry for a diagnostic below a
  newly unbaselined one, and a rename edits those lines
- **THEN** exactly the entries basedpyright matched are rewritten, and `la-typecheck` reports the same new errors
  as before the rename

#### Scenario: Configured command with a project flag
- **WHEN** `commands.typecheck.python` is `basedpyright -p .` and the rename edits a baselined line
- **THEN** the entry is realigned

#### Scenario: Moved module
- **WHEN** `move-module` moves `pkg/a.py`, which has baseline entries, into `pkg/sub/`
- **THEN** those entries are listed under `./pkg/sub/a.py` and `la-typecheck` passes

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

### Requirement: Python rename refusals are findings
When rope refuses to rename the location, the Python `dr-refactor` SHALL report the `refactor.cannot-rename` finding
for that entry on stderr, write nothing and exit 1. No traceback or library message text SHALL be printed.

#### Scenario: Location that is not an identifier
- **WHEN** `rename --offset` points at whitespace between two statements
- **THEN** stderr ends with the `refactor.cannot-rename` finding and the exit code is 1
