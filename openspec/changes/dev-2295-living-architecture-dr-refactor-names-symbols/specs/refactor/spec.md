## ADDED Requirements

### Requirement: Symbols are located by their path in a file
`dr-refactor rename`, `retarget` and `move-symbol` SHALL accept `--symbol Q`, the path of a declaration inside
`--file`, in both languages. Q SHALL be segments joined by `.`, where `<locals>` steps into a function's body, a
trailing `(param)` names a parameter of the function the path names, and a trailing `['value']` or `["value"]`
names the member `value` of a string-literal type in the annotation or alias body of the declaration the path
names. At most one of `--offset`, `--line` and `--symbol` SHALL be given (a usage error, exit 2, otherwise).

The declarations a path SHALL reach are, in Python: module-level names (def, class, assignment, import binding),
class-body names (def, property, class, assignment, annotated field), `self.NAME` assignments in the class's methods
(as `Class.NAME` when the class body does not declare NAME), function locals and parameters; in TypeScript:
top-level functions, classes, interfaces, type aliases, enums, namespaces and variables, the members of a class,
interface, type literal (through an alias of it), enum or namespace, the locals of a function, method or
arrow-function body, and parameters.

Declarations the checker resolves to one symbol (overloads, property accessors, redefinitions in one scope, merged
TypeScript declarations) SHALL be one symbol, located at the first. A path that resolves to no declaration SHALL
exit 2 with `refactor.symbol-unresolved`, listing the names its deepest resolved scope declares; a path that
resolves to declarations of more than one symbol SHALL exit 2 with `refactor.symbol-ambiguous`, listing each
candidate's `path:line`. `move-symbol --symbol` SHALL accept only a top-level declaration.

#### Scenario: Method by path
- **WHEN** `rename --file src/pkg/storage.py --symbol StorageBackend.get_model --new-name load_model` runs
- **THEN** the result equals the same rename located by `--line`/`--col` at the method's name

#### Scenario: Nested function, parameter and field
- **WHEN** paths `build.<locals>.inner`, `StorageBackend.get_model(model_name)` and `_ProjectionPlan.measures`
  are renamed in turn
- **THEN** each renames that declaration and its references, and never a same-named declaration elsewhere in the
  file

#### Scenario: Instance attribute by class path
- **WHEN** `class C` assigns `self.cache = {}` in `__init__` and its body declares no `cache`, and `--symbol C.cache`
  is renamed
- **THEN** the assignment and every reference the checker resolves to it are renamed

#### Scenario: Import binding
- **WHEN** `--symbol Engine` names `from pkg.engine import Engine` in an importing file
- **THEN** the rename equals the rename located at the class declaration

#### Scenario: Overloads and accessors are one symbol
- **WHEN** a path names a function with `@overload` signatures, or a property with a setter
- **THEN** it is located without an ambiguity finding and every declaration is renamed

#### Scenario: Unresolved path lists candidates
- **WHEN** `--symbol StorageBackend.get_modle` runs and `StorageBackend` declares `get_model` and `save_model`
- **THEN** stderr is `refactor.symbol-unresolved` listing `get_model, save_model`, the exit code is 2 and nothing
  changes

#### Scenario: Ambiguous path lists candidates
- **WHEN** a module defines `class C` twice and `--symbol C.run` runs
- **THEN** stderr is `refactor.symbol-ambiguous` listing both `path:line` sites and the exit code is 2

#### Scenario: Two locators refused
- **WHEN** `--symbol foo --line 3` are both given
- **THEN** it exits 2 as a usage error

#### Scenario: TypeScript member and local by path
- **WHEN** `--symbol Store.getModel`, `--symbol build.<locals>.inner` and `--symbol Kind['edit_model']` run in
  TypeScript
- **THEN** each locates that declaration, through either invoking twin

### Requirement: Rename maps apply many renames as one
`dr-refactor rename-map MAP` SHALL read MAP (a path relative to the working directory) as a YAML list of entries
valid against the shared rename-map schema: `file` relative to `--project`, exactly one locator (`symbol`, `line`
with an optional `col`, or `offset`), and exactly one of `new_name` or `retarget` (a `symbol` in the same file). An
invalid map SHALL exit 2 with `refactor.map-invalid` naming the entry index. It SHALL take `rename`'s options other
than the locator and `--new-name`, applying to every entry. All entries SHALL be of one language, else exit 2 with
`refactor.map-mixed-languages`; the map runs in that language's twin.

Every locator SHALL be resolved against the code before any entry is computed, so entries name old names. Two
entries resolving to one symbol with the same intent SHALL merge; with different intents they SHALL exit 2 with
`refactor.map-duplicate` naming both entry indexes. Every entry SHALL then be computed on one snapshot of the
project, every rename rule running once over the union of the entries' symbols, with one blind-spot scan for every
member entry's old name and one combined refusal report, sorted as a single rename sorts it. Identical edits SHALL
merge; two entries rewriting one span differently SHALL exit 1 with `refactor.map-conflict` naming the site and
both entries, writing nothing. Name-conflict checks SHALL run against the code before the map, so a swap or a chain
of names inside one scope is refused. A retarget entry whose target another entry renames SHALL write the target's
new name.

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
- **THEN** stderr lists both blind spots in path, line and column order, followed by one `refactor.blindspots`
  line, the exit code is 1 and nothing changes

#### Scenario: Duplicate entries
- **WHEN** two entries locate the same method with new names `a` and `b`
- **THEN** stderr is `refactor.map-duplicate` naming both entry indexes and the exit code is 2

#### Scenario: Conflicting edits
- **WHEN** one entry renames `Base.save` to `store` and another renames `Sub.save`, its override, to `keep`
- **THEN** stderr is `refactor.map-conflict` naming a shared site and both entries, the exit code is 1 and nothing
  changes

#### Scenario: Swap in one scope refused
- **WHEN** a map renames parameter `f(x)` to `y` and `f(y)` to `x`
- **THEN** the rename refuses with the existing name-conflict finding and nothing changes

#### Scenario: Mixed languages
- **WHEN** a map holds a `.py` and a `.ts` entry
- **THEN** stderr is `refactor.map-mixed-languages` and the exit code is 2

#### Scenario: Invalid map
- **WHEN** entry 2 carries both `new_name` and `retarget`
- **THEN** stderr is `refactor.map-invalid` naming entry 2 and the exit code is 2

#### Scenario: Single rename equals its map
- **WHEN** `rename --file F --symbol Q --new-name N` and a map holding that one entry run on the same project
- **THEN** their stdout, stderr and exit codes are identical, through either invoking twin

### Requirement: Retarget rewrites references to an alias
`dr-refactor retarget --file F --symbol ALIAS --target TARGET` (and a map entry with `retarget`) SHALL rewrite every
reference the rename of ALIAS to TARGET's name would rewrite, every rename rule included, except the edits at
ALIAS's own declarations; ALIAS SHALL stay declared and unchanged. ALIAS and TARGET SHALL be declared in the same
class body or module scope, else exit 2 with `refactor.retarget-scope`. Checks that the new name is already used
SHALL NOT apply. A member ALIAS SHALL refuse, exit 1 with one `refactor.retarget-override` line per site, while a
class of its hierarchy other than ALIAS's own declares ALIAS's name. A bare-name reference at which TARGET's name
is bound to something else SHALL refuse with `refactor.retarget-shadowed`. An import that the rewrite would make a
duplicate of an import of TARGET from the same module SHALL be removed instead.

#### Scenario: Method twin
- **WHEN** `class Engine` declares `save_model` and a deprecated `def save(self, m: Model) -> None: return
  self.save_model(m)`, code calls `engine.save(m)` with `engine: Engine`, and `retarget --symbol Engine.save
  --target Engine.save_model` runs
- **THEN** the call becomes `engine.save_model(m)` and `Engine.save` is unchanged

#### Scenario: Class twin and its imports
- **WHEN** `models.py` declares `AcmeModel = Model` and a module holds `from pkg.models import Model,
  AcmeModel` and uses `AcmeModel()`
- **THEN** after retargeting `AcmeModel` to `Model` the import is `from pkg.models import Model` and the use is
  `Model()`

#### Scenario: Other scope refused
- **WHEN** ALIAS is declared in `compat.py` and TARGET in `core.py`
- **THEN** stderr is `refactor.retarget-scope` and the exit code is 2

#### Scenario: Overridden alias refused
- **WHEN** a subclass of `Engine` overrides `save`
- **THEN** stderr names that override with `refactor.retarget-override`, the exit code is 1 and nothing changes

#### Scenario: Shadowed target refused
- **WHEN** a function binds a local `Model` and uses `AcmeModel()` in its body
- **THEN** stderr names that use with `refactor.retarget-shadowed` and the exit code is 1

#### Scenario: TypeScript merged alias
- **WHEN** a TypeScript class declares `/** @deprecated */ get old(): number { return this.value; }` and `value`,
  and `retarget --symbol C.old --target C.value` runs
- **THEN** every `c.old` read becomes `c.value` and the accessor is unchanged

### Requirement: An apply writes every file or none
`dr-refactor --apply` SHALL re-check, immediately before writing, that no file it writes changed since it was read,
and SHALL write each file through a temporary file in the same directory renamed over it. When any write fails, the
files already written SHALL be restored, a finding SHALL be printed and the exit code SHALL be 1.

#### Scenario: Failed write rolls back
- **WHEN** a map's apply fails while writing its third file
- **THEN** the first two files hold their original bytes and the exit code is 1

### Requirement: Refactors keep the type-check baseline aligned
Every `dr-refactor` subcommand SHALL keep the baseline of each language it edits aligned, when that language's
`commands.typecheck` entry is set and its `baseline_file` exists at the repo root and lists a file the refactor
affects. A baselined diagnostic that the refactor moves, by an edit on its line, a moved file or a moved
declaration, SHALL stay baselined; no diagnostic SHALL become baselined that was not. The baseline SHALL appear in
the printed diff and be written with the sources, in dry-run and `--apply` alike. Diagnostic ranges SHALL be mapped
through the refactor's edits; a start or end at or inside a replaced span SHALL map to the replacement's start or
end.

- Python (`.basedpyright/baseline.json`): the baselined diagnostics and the entries they match SHALL be those
  basedpyright itself matches, from running the configured command over the affected files once with a temporary
  copy of the baseline and once with an empty one; the project's baseline SHALL NOT be written by the checker. Each
  matched entry whose file, columns or line count change SHALL be rewritten in place, or inserted at its sorted
  position in its new file.
- TypeScript (`.tsc-baseline.json`): the before and after diagnostics SHALL be the pre-emit diagnostics, from the
  bundled language services of every project holding the file, of every file the baseline lists, before and after
  the edits applied in memory, keyed as `la-typecheck` keys tsc's output. A baselined key whose instances all map to
  one new key SHALL move its count there.

A diagnostic whose range cannot be mapped, or a TypeScript key whose instances map to different keys while only
some are baselined, SHALL leave its entry unchanged and print `refactor.baseline-ambiguous` on stderr, without
changing the exit code. A checker run that fails SHALL exit 1 with `refactor.baseline-failed` naming the language
and write nothing.

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
- **THEN** no checker runs and the output equals the rename without alignment

#### Scenario: Checker failure
- **WHEN** the configured command cannot run
- **THEN** stderr is `refactor.baseline-failed` naming `python`, the exit code is 1 and nothing is written

### Requirement: Literal members are renamed where the checker types them
A rename located at a member of a string-literal type (`--symbol Q['value']`, or a locator on that string inside
the type) SHALL take the new value from `--new-name`: any text without a quote character, backslash or line break
(else exit 2 with `refactor.literal-value`); the identifier rule SHALL NOT apply, and each rewritten string SHALL
keep its quote style.

- TypeScript: the rewritten strings SHALL be the language service's rename locations for that string.
- Python: the rename SHALL probe the checker in la's language server, in memory, with the member replaced by a
  sentinel. A string literal exactly OLD SHALL be rewritten when, under the probe, a new diagnostic's range is that
  literal or a list, tuple, set or dict display holding it as an element or key, or when the hover type of its
  comparison operand (`==`, `!=`, `is`, `is not`), `in` container or `match` subject contains the sentinel. With the
  member and every such literal set to the sentinel, each diagnostic absent before the probe SHALL be a blind spot,
  `refactor.literal-unresolved`, joining the blind-spot refusal (`--keep` and `--allow-blindspots` apply).

With `--docs`, every other string equal to OLD SHALL be listed as a `leftover` with `{where}` `string`.

#### Scenario: Python contexts
- **WHEN** `DriftKind = Literal["edit_model", "drop"]` is renamed at `DriftKind['edit_model']` to `edit_master`, and
  the project holds a call `f("edit_model")` with `f(kind: DriftKind)`, `k: DriftKind = "edit_model"`, a return
  of `"edit_model"` from a function returning `DriftKind`, a default `kind: DriftKind = "edit_model"`, `xs:
  list[DriftKind] = ["edit_model"]`, `kind == "edit_model"`, `kind in ("edit_model",)` and `case "edit_model":`
  on a `DriftKind` subject
- **THEN** every one of those strings becomes `"edit_master"`, with its quote style kept

#### Scenario: Unrelated equal strings untouched
- **WHEN** the project also holds `Other = Literal["edit_model", "zzz"]` with `g("edit_model")` for `g(o: Other)`,
  `s: str = "edit_model"` and `choices=["edit_model"]`
- **THEN** none of them changes, and with `--docs` the `str` and `choices` strings are listed as `leftover`

#### Scenario: Exhaustive match does not refuse
- **WHEN** a `match` on a `DriftKind` subject handles every value and ends with `assert_never(kind)`
- **THEN** its `case "edit_model":` is rewritten and no blind spot is reported

#### Scenario: Narrowed local refuses
- **WHEN** a function holds `k = "edit_model"` and later `f(k)`
- **THEN** the call site is a `refactor.literal-unresolved` blind spot and the rename refuses with exit 1

#### Scenario: Derived alias
- **WHEN** `Ext = Literal[DriftKind, "x"]` types an argument `h("edit_model")`
- **THEN** that string is rewritten

#### Scenario: TypeScript contexts
- **WHEN** `type Kind = 'edit_model' | 'drop'` is renamed at `Kind['edit_model']`, and the project holds a typed
  variable, an argument, `x === 'edit_model'`, a `case`, a typed array element, an equal string in another union,
  a `string` variable and an imported use of `Kind`
- **THEN** the typed variable, argument, comparison, case, array element and imported use change, and the other
  union's string and the `string` variable do not

#### Scenario: Value with a quote refused
- **WHEN** `--new-name` is `it's`
- **THEN** stderr is `refactor.literal-value` and the exit code is 2

### Requirement: --docs lists compound names
With `--docs`, a rename, retarget or map SHALL list every declaration, in a project source file of its language,
whose name contains OLD as a word sequence, with one `refactor.compound` line per declaration, sorted with the other
leftovers; listing SHALL NOT change the exit code or the name. Names SHALL split into words at `_` and at CamelCase
boundaries (a run of capitals is one word), compared case-insensitively, the last word of OLD also matching with an
`s` or `es` suffix. OLD itself and every name the refactor renames SHALL NOT be listed.

#### Scenario: Compound names listed
- **WHEN** `Model` is renamed to `Dataset` with `--docs` and the project declares `ModelMeasures`, `AcmeModels`,
  `TestModelMeasurePosition`, `model_name` and `Modelling`
- **THEN** the first four are listed with `refactor.compound` and `Modelling` is not

#### Scenario: Snake case and plural
- **WHEN** `column` is renamed with `--docs` and the project declares `get_columns` and `ColumnCycleError`
- **THEN** both are listed

#### Scenario: Without --docs
- **WHEN** the same rename runs without `--docs`
- **THEN** no compound name is listed

### Requirement: dr-compliance --attr takes several names
`dr-compliance --attr` SHALL be repeatable. One scan SHALL report the blind spots of every given name, sorted by
path, line, column and then name, in both languages.

#### Scenario: Two names
- **WHEN** `dr-compliance --select attr-blindspot --attr get_model --attr save_model tests` runs where untyped
  receivers access both
- **THEN** both names' blind spots are reported in one sorted block and the exit code is 1

### Requirement: dr-mock-lint compares with a base branch
`dr-mock-lint` SHALL be a parsed command: positional paths and `--base BRANCH`; `--help` SHALL print its help and
exit 0. With `--base`, it SHALL compare with `origin/BRANCH` after the shared best-effort fetch, as
`la-affected-tests` does, exiting 2 only when `origin/BRANCH` does not resolve. It SHALL lint the given files as they
are and the same files at the base, read from git without checking anything out (paths mapped through git's rename
detection), and SHALL print only the findings whose count, keyed by path, template and parameters other than the
line, exceeds the base's. The exit code SHALL be 1 iff it prints a finding.

#### Scenario: Help
- **WHEN** `dr-mock-lint --help` runs through either twin
- **THEN** it prints the help and exits 0

#### Scenario: Only new findings
- **WHEN** `tests/test_a.py` has an unspec'd `Mock()` at the base and the change adds a second one and moves the
  first down by three lines
- **THEN** with `--base main` only the added one is printed and the exit code is 1

#### Scenario: Renamed file
- **WHEN** the change renames `tests/test_a.py` to `tests/test_b.py` without touching its findings
- **THEN** with `--base main` nothing is printed and the exit code is 0

#### Scenario: TypeScript at the base
- **WHEN** a TypeScript test's `vi.fn()` double was untyped at the base and stays so
- **THEN** with `--base main` it is not printed

## MODIFIED Requirements

### Requirement: dr-* inputs are routed by file language
`dr-refactor`, `dr-compliance` and `dr-mock-lint` SHALL route each input file to the twin of its language,
decided by the registry's source extensions. `dr-refactor`'s language SHALL be the language of `--file`
(`rename`, `retarget`, `move-symbol`), of every entry's `file` (`rename-map`) or of `--module` (`move-module`); a
source of an unregistered extension, a `--dest` of another language, or a `--module` directory whose expansion
holds more than one language, SHALL exit 1 with a finding. For `dr-compliance` and `dr-mock-lint`, an explicit file
of an unregistered extension, or matching the language's `declaration_globs`, SHALL be skipped with a warning on
stderr; a directory SHALL expand only to files of the repo's languages, or of every registered language when the
repo has none, excluding `declaration_globs` and `excluded_dirs`. The other language's files SHALL run in its twin
with the same working directory and the same options. Output SHALL be one block per language in registry id order,
each exactly as that language's twin prints it alone; stderr SHALL be relayed; the exit code SHALL be the maximum.
When the other twin cannot run or fails with exit 2 or a signal, the command SHALL print nothing on stdout, report
the failure as the forwarding rules define, and exit 2.

#### Scenario: Python-only repo directory expansion is unchanged
- **WHEN** `dr-compliance src` runs in a repo whose only repo language is Python and `src` also holds `app.js`
- **THEN** only the `.py` files are checked and stdout equals today's golden

#### Scenario: Mixed explicit files
- **WHEN** `dr-mock-lint tests/test_a.py web/a.test.ts` runs through either twin, both files violating
- **THEN** stdout is the Python block followed by the TypeScript block, identical for both invoking twins, and the exit code is 1

#### Scenario: Declaration file skipped
- **WHEN** `dr-compliance types/api.d.ts` runs
- **THEN** a warning names the skipped file on stderr and the exit code is 0

#### Scenario: Relative paths from a subdirectory
- **WHEN** `dr-refactor --project .. rename --file src/a.ts --symbol foo --new-name bar` runs through the PyPI twin from a subdirectory
- **THEN** the forwarded run resolves every path against the same working directory and the output equals the npm twin's own run

#### Scenario: Cross-language destination
- **WHEN** `dr-refactor move-symbol --file pkg/a.py --symbol foo --dest web/b.ts` runs
- **THEN** it exits 1 with the cross-language finding and changes nothing

#### Scenario: Mixed-language directory refused
- **WHEN** `dr-refactor move-module --module pkg --dest lib` runs and `pkg` holds both `.py` and `.ts` sources
- **THEN** it exits 1 with a mixed-language finding and changes nothing

#### Scenario: TypeScript map through the PyPI twin
- **WHEN** `dr-refactor rename-map map.yaml` runs through the PyPI twin and every entry names a `.ts` file
- **THEN** the output and exit code equal the npm twin's own run

#### Scenario: Base comparison in both blocks
- **WHEN** `dr-mock-lint --base main tests/test_a.py web/a.test.ts` runs through either twin
- **THEN** each language's block holds only its new findings, identical for both invoking twins

### Requirement: Refactor output format
`dr-refactor` SHALL print one header line per refactor entry in order (a rename map's entries in map order), then
one unified diff per changed file sorted by path (`--- a/<path>`, `+++ b/<path>`, three context lines, no
end-of-file marker), the type-check baseline included, a `rename from` / `rename to` pair for every moved file, then
the dry-run or applied footer. Refusals, leftovers and warnings SHALL be printed on stderr. Every header, footer,
warning and error SHALL come from the findings registry; no checker or library message text SHALL be printed. The
diff format SHALL be pinned by shared vectors that both twins pass, covering a missing final newline, CRLF line
endings, created and deleted files, and paths with spaces or non-ASCII characters.

#### Scenario: TS rename dry-run
- **WHEN** `dr-refactor rename --file src/a.ts --symbol foo --new-name bar` runs on a project where `src/b.ts` imports `foo`
- **THEN** stdout is the rename header, the diffs of `src/a.ts` and `src/b.ts` in path order, and the dry-run footer naming 2 files, and no file changes

#### Scenario: Map headers
- **WHEN** a map holds a rename entry and then a retarget entry
- **THEN** stdout starts with the rename header line and then the retarget header line

#### Scenario: Diff vectors
- **WHEN** either twin's suite runs
- **THEN** its diff formatter reproduces every shared diff vector byte for byte

### Requirement: TypeScript locators
`--line` and `--col` SHALL be 1-based and `--offset` 0-based; columns and offsets SHALL count Unicode code
points, and a column SHALL count within its line excluding the line terminator. A line, column or offset out
of range SHALL exit 1 with a finding. `--symbol` SHALL locate as the symbol-path requirement defines. No locator
SHALL exit 1 with the no-locator finding.

#### Scenario: Astral character before the symbol
- **WHEN** a line is `const s = "😀"; const foo = 1;` and `--line 1 --col 22` points at `foo`
- **THEN** `foo` is renamed

#### Scenario: Column out of range
- **WHEN** `--col` exceeds the line's length plus one
- **THEN** it exits 1 with the out-of-range finding

### Requirement: TypeScript move-symbol and move-module
`move-symbol` SHALL apply the language service's move-to-file refactor for a top-level declaration into the
existing `--dest` file, rewriting every import of it. Every re-export of the moved symbol, named, default or
through `export *`, SHALL resolve to the new file. A location with no applicable move SHALL exit 1 with a
not-movable finding. `move-module` SHALL move a file or directory into the existing `--dest` directory and
rewrite every import of it.

#### Scenario: Move a function with importers
- **WHEN** `--apply move-symbol --file src/a.ts --symbol foo --dest src/b.ts` runs and `src/c.ts` imports `foo` from `./a`
- **THEN** `foo` is in `src/b.ts`, `src/c.ts` imports it from `./b`, and the applied footer lists the changed files

#### Scenario: Default export and re-export
- **WHEN** the moved symbol is a default export re-exported by `src/index.ts`
- **THEN** every importer and the re-export resolve to the new file

#### Scenario: Barrel re-export
- **WHEN** `src/index.ts` has `export * from './a'` and `foo` moves from `src/a.ts` to `src/b.ts`
- **THEN** `src/index.ts` re-exports `foo` from `./b`

#### Scenario: Not movable
- **WHEN** the location is inside a function body
- **THEN** it exits 1 with the not-movable finding

#### Scenario: Move a directory
- **WHEN** `--apply move-module --module src/util --dest src/lib` runs
- **THEN** `src/util` becomes `src/lib/util` and every import of it is rewritten

### Requirement: A Python dry-run writes nothing
The Python `dr-refactor` without `--apply` SHALL leave the project tree unchanged. In particular it SHALL NOT
create rope's `.ropeproject` folder. With `--apply`, it SHALL change only the files the refactor rewrites,
creates, moves or deletes, and the type-check baseline it realigns.

#### Scenario: No rope folder after a dry-run
- **WHEN** `dr-refactor rename --file pkg/a.py --symbol foo --new-name bar` runs on a project without `.ropeproject`
- **THEN** the project still has no `.ropeproject` and no file changes

#### Scenario: No rope folder after an apply
- **WHEN** the same rename runs with `--apply`
- **THEN** only the renamed files change and no `.ropeproject` is created

### Requirement: Python async definitions rename like sync ones
The Python `dr-refactor rename` SHALL rename an `async def` method or function located by `--line`/`--col`,
`--offset` or `--symbol`, at its definition or at a call: its definition, its overrides in the renamed hierarchy
and every call it would rename for the same code without `async`.

#### Scenario: Async method from its definition
- **WHEN** `class A` has `async def get_model(self, x: int) -> None: ...`, `class B(A)` overrides it with an `async
  def`, and a function holds `a = A()` and `await a.get_model(1)`, and the rename names `get_model` in `A` by
  `--line`/`--col`
- **THEN** both definitions and the call are renamed and the exit code is 0

#### Scenario: Async function from a call
- **WHEN** a module-level `async def fetch()` is renamed by `--offset` of one of its calls
- **THEN** the definition and every call are renamed

#### Scenario: Async method by path
- **WHEN** the same method is renamed by `--symbol A.get_model`
- **THEN** the result equals the `--line`/`--col` rename

### Requirement: Python parameter renames cover every parameter kind
The Python `dr-refactor rename` SHALL rename a `def` or `async def` parameter of any kind (positional-only,
positional-or-keyword, keyword-only, `*args`, `**kwargs`) located by `--line`/`--col`, `--offset` or `--symbol`, at
its declaration, at a use in its function or at a `name=` keyword of a call. It SHALL rewrite each renamed
declaration, every use of it in its function including nested scopes, and every `name=` keyword at a call the
checker resolves to a renamed declaration. A `name=` keyword SHALL resolve only to a positional-or-keyword or
keyword-only parameter, never to a positional-only parameter, `*args` or `**kwargs`. Positional arguments, keywords
that reach the function unresolved (`**mapping` unpacking, `**kwargs` forwarding) and every other text SHALL be
unchanged.

#### Scenario: Keyword-only parameter of a function
- **WHEN** `def kwonly(*, model_name: str) -> str: return model_name` has its parameter renamed to `dataset_name`,
  and a module elsewhere in the project calls `kwonly(model_name="x")`
- **THEN** the declaration, the body use and the call's keyword are renamed, and the exit code is 0

#### Scenario: Keyword-only parameter after *args
- **WHEN** `def star(*xs: int, model_name: str) -> str` has `model_name` renamed and a call is
  `star(1, 2, model_name="x")`
- **THEN** the declaration, its body uses and the keyword are renamed, and `1, 2` are unchanged

#### Scenario: Keyword-only parameter of a method through an annotated receiver
- **WHEN** `C.kmeth(self, *, model_name: str)` has `model_name` renamed and a function `use(c: C)` calls
  `c.kmeth(model_name="y")`
- **THEN** the declaration, its body uses and the keyword are renamed

#### Scenario: Async method keyword-only parameter
- **WHEN** `async def fetch(self, *, model_name: str)` of class `C` has `model_name` renamed and a function awaits
  `c.fetch(model_name="y")` with `c: C`
- **THEN** the declaration, its body uses and the keyword are renamed

#### Scenario: Positional-only parameter
- **WHEN** `def posonly(model_name: str, /) -> str: return model_name` has its parameter renamed and a call is
  `posonly("x")`
- **THEN** the declaration and the body use are renamed and the call is unchanged

#### Scenario: Located at a call keyword
- **WHEN** the rename locates `model_name` by `--line`/`--col` at the keyword of `kwonly(model_name="x")`
- **THEN** the declaration, the body use and every resolved keyword are renamed

#### Scenario: Located by path
- **WHEN** the rename locates it by `--symbol kwonly(model_name)`
- **THEN** the result equals the rename located at its declaration

#### Scenario: Mixed-kind signature
- **WHEN** `def f(a: int, /, b: int, *xs: int, c: int = 0, **kw: int) -> int` uses each parameter in its body, the
  project calls `f(1, 2, 3, c=4, d=5)`, `f(1, b=2)` and `f(1, 2, a=3)`, and `b` and then `c` are renamed
- **THEN** each rename changes its declaration, its body uses and its own keywords only (`b=2` for `b`, `c=4` for
  `c`); `a=3` and `d=5` are unchanged

#### Scenario: Keywords that do not bind the parameter are unchanged
- **WHEN** `def g(a: int, /, *args: int, **kwargs: int) -> None` has `a`, then `args`, then `kwargs` renamed, and the
  project calls `g(1, a=2, args=3, kwargs=4)`
- **THEN** each rename changes its declaration and body uses only, and every keyword of the call is unchanged

#### Scenario: Unresolved keyword sites are unchanged
- **WHEN** `kwonly`'s `model_name` is renamed and the project holds `kwonly(**{"model_name": "x"})`, a wrapper
  `def wrap(**kw: str) -> str: return kwonly(**kw)` called as `wrap(model_name="x")`, and
  `functools.partial(kwonly, model_name="x")`
- **THEN** the `**mapping` and `wrap` sites are unchanged, and the `functools.partial` keyword, which the checker
  resolves to `kwonly`, is renamed

#### Scenario: Other refactors over mixed-kind signatures
- **WHEN** a module holds `def f(a: A, /, *, b: A) -> None` whose body calls `a.get_model()` and `b.get_model()`,
  and method `A.get_model` is renamed, and separately `f` is moved to another module with `move-symbol`
- **THEN** the rename renames both calls, and the move rewrites `f`'s imports and calls exactly as for a function
  with positional-or-keyword parameters
