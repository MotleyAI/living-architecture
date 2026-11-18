## MODIFIED Requirements

### Requirement: --docs rewrites mentions in comments, docstrings, strings and prose files
`dr-refactor rename --docs` (any symbol other than a module, both languages) SHALL scan the comments and string
literals (Python docstrings and f-string literal parts; TypeScript JSDoc and template-literal text) of every source
file of the rename's language under the project, and the files `config` lists for the project (tracked and
untracked-not-ignored; none outside git) whose extension is among `dr-refactor`'s prose extensions in the shared
contract (`.md`, `.rst`, `.txt`). A mention SHALL be an occurrence of OLD not adjacent to an identifier character.

Every mention SHALL be resolved once over all entries of the run, to exactly one entry, whose new name it takes, or
to none, in which case it is listed. A mention SHALL never be refused with `refactor.map-conflict`.

- A qualified mention SHALL be rewritten in every scanned file: `Owner.OLD`, or `Owner#OLD` in TypeScript, where
  `Owner` names a class of the renamed hierarchy (or, for a module-level symbol, the declaring module's last
  segment), optionally preceded by dotted segments that SHALL form a suffix of the declaring module's dotted path
  (Python: the module's name from its source folder; TypeScript: the file's project-relative path without its
  source extension, `/` read as `.`).
  With such a prefix it SHALL be rewritten only when no other project class with that simple name that declares
  OLD sits in a module whose dotted path also ends with those segments; otherwise it SHALL be listed.
  Without such a prefix it SHALL be rewritten only when no other project class with that simple name declares OLD;
  otherwise it SHALL be listed.
- A bare mention SHALL be code-marked when it is inside single or double backticks, optionally followed by `()`, or
  is the target of a Sphinx role or of `{@link OLD}`. In a declaring file (a source file holding a renamed
  declaration, `--with` stand-ins included), a code-marked bare mention SHALL be decided by its owning class:
  - A class SHALL own its declaration's span: in Python the class statement from its first decorator to its end; in
    TypeScript the class, interface or type-literal declaration and the JSDoc comments the compiler attaches to it.
  - The owning class of a mention SHALL be the innermost class owning its position whose member lookup (Python's
    method resolution order; TypeScript's property lookup, over every merged declaration) finds OLD.
  - With an owning class, the mention SHALL be rewritten when that lookup lands only on declarations the run renames
    to one new name, and take that name. It SHALL be listed when the lookup lands on a declaration the run leaves
    unchanged, on declarations renamed to different names, or cannot be completed (an unresolved base before OLD is
    found).
  - Without an owning class, the mention SHALL be rewritten when every module-level and class-member declaration of
    OLD in that file is renamed by the run, all to one new name, and take that name; otherwise it SHALL be listed.
- Every other mention SHALL be listed: one `refactor.leftover` line per mention on stderr, sorted by path, line and
  column, with `{where}` one of `comment`, `docstring`, `string`, `prose`. Listing SHALL NOT change the exit code.
- Only the characters of OLD SHALL change. A mention another rule already rewrote SHALL NOT be listed.

Without `--docs`, comments, docstrings, prose files and strings other than the forms of the other requirements
SHALL be unchanged and unlisted, with one exception: a member rename SHALL list, as `refactor.leftover` with
`{where}` `string`, each string literal whose whole value is OLD (Python: not a docstring or f-string; TypeScript: a
string literal or a template literal without substitutions) that no other rule rewrote or refused on and that is
not the member or target argument of a string-member form or patch target. Listing SHALL NOT change the exit code.

#### Scenario: Qualified and code-marked mentions
- **WHEN** `SearchQueryEngine.recommend_root_model` is renamed with `--docs`, a docstring elsewhere holds
  ``:meth:`SearchQueryEngine.recommend_root_model` ``, the engine's class docstring holds ``` ``recommend_root_model`` ```,
  and `docs/api.md` holds `pkg.engine.SearchQueryEngine.recommend_root_model`
- **THEN** all three mentions are rewritten

#### Scenario: A plain word opening a string is listed
- **WHEN** the same rename runs and the engine's module holds `"recommend_root_model: no candidates"` as a message
  and `f"recommend_root_model of {x}"`
- **THEN** neither string changes and both are listed as `leftover` with `{where}` `string`

#### Scenario: Bare words listed
- **WHEN** a comment in another module says `# calls recommend_root_model first` and the engine's module has a
  comment `# then recommend_root_model runs`
- **THEN** neither changes and both are listed as `leftover` with `{where}` `comment`

#### Scenario: Another class's docstring in the declaring file
- **WHEN** `A.field` is renamed to `column` with `--docs`, the same file declares class `B` with its own `field`
  passed with `--without`, and both class docstrings hold ``` ``field`` ```
- **THEN** `A`'s docstring holds ``` ``column`` ```, `B`'s is unchanged and listed as `leftover`, and the exit code
  is 0

#### Scenario: TypeScript JSDoc of another class
- **WHEN** `Table.columns` is renamed to `fields` with `--docs`, the same file declares `Result` with its own
  `columns` passed with `--without`, and each class's JSDoc holds `` `columns` ``
- **THEN** `Table`'s JSDoc is rewritten, and `Result`'s is unchanged and listed as `leftover` with `{where}`
  `comment`

#### Scenario: Module-level mention beside an unrenamed declaration
- **WHEN** the same Python rename runs and the module docstring holds ``` ``field`` ```
- **THEN** the module docstring is unchanged and listed as `leftover` with `{where}` `docstring`

#### Scenario: Module-level mention with one renamed declaration
- **WHEN** `A.field` is renamed with `--docs`, no other declaration in its file is named `field`, and the module
  docstring holds ``` ``field`` ```
- **THEN** the module docstring is rewritten

#### Scenario: Inherited member
- **WHEN** `Base.field` is renamed with `--docs` and, in the same file, `Sub(Base)` does not declare `field` and
  its docstring holds ``` ``field`` ```
- **THEN** `Sub`'s docstring is rewritten

#### Scenario: Class without the member
- **WHEN** `A.field` is renamed with `--docs`, no other declaration in its file is named `field`, and a class
  `Helper` in that file, with no member `field`, holds ``` ``field`` ``` in its docstring
- **THEN** `Helper`'s docstring is rewritten, as a mention without an owning class

#### Scenario: Two entries, each class's own docstring
- **WHEN** a map renames `Table.columns` to `fields` and `Result.columns` to `result_columns` with `--docs`, and each
  class's docstring (Python) or JSDoc (TypeScript) holds the code-marked `columns`
- **THEN** each is rewritten to its own class's new name, in both twins, and the exit code is 0

#### Scenario: Two entries reaching a module-level mention
- **WHEN** the same map runs and the module docstring (Python) or a comment outside both classes (TypeScript) holds
  the code-marked `columns`
- **THEN** it is unchanged and listed once as `leftover`, no `refactor.map-conflict` is printed, both entries apply
  and the exit code is 0, in both twins

#### Scenario: Unresolved base before the member
- **WHEN** `A.field` is renamed with `--docs` and, in the same file, class `C(Unknown, A)` with `Unknown` unresolved
  holds ``` ``field`` ``` in its docstring
- **THEN** that docstring is unchanged and listed as `leftover`

#### Scenario: Simple-name collision
- **WHEN** another project class also named `SearchQueryEngine` declares `recommend_root_model` and is passed with
  `--without`, and a comment says `SearchQueryEngine.recommend_root_model`
- **THEN** that mention is listed, not rewritten, while `engine.SearchQueryEngine.recommend_root_model` (matching
  the declaring module's path) is rewritten

#### Scenario: Prefix shared by two modules
- **WHEN** `pkg1.engine.SearchQueryEngine.recommend_root_model` is renamed, `pkg2.engine.SearchQueryEngine` also
  declares `recommend_root_model` and is passed with `--without`, and a comment says
  `engine.SearchQueryEngine.recommend_root_model`
- **THEN** that mention is listed, while `pkg1.engine.SearchQueryEngine.recommend_root_model` is rewritten

#### Scenario: Git-ignored prose skipped
- **WHEN** `build/notes.md` is git-ignored and mentions `SearchQueryEngine.recommend_root_model`
- **THEN** it is unchanged and unlisted

#### Scenario: TypeScript JSDoc link
- **WHEN** `Engine.saveModel` is renamed with `--docs` and a JSDoc comment holds `{@link Engine#saveModel}`
- **THEN** the link is rewritten

#### Scenario: Without --docs
- **WHEN** the same rename runs without `--docs`
- **THEN** no comment, docstring, message or prose file changes and nothing is listed

#### Scenario: Exact string literal listed without --docs
- **WHEN** `Storage.get_model` is renamed without `--docs` and a module holds `attrgetter("get_model")` and
  `"get_model is slow"`
- **THEN** both are unchanged, the first is listed as `leftover` with `{where}` `string`, the second is not, and the
  exit code is 0

## ADDED Requirements

### Requirement: --docs-pick rewrites the listed mentions of a line
`dr-refactor rename` and `rename-map` SHALL accept `--docs-pick PATH:LINE[=ENTRY]` (repeatable, both languages).
PATH SHALL be resolved as `--keep` resolves it. ENTRY SHALL be a 1-based entry index of the map; a `rename` is
entry 1. The selectable site SHALL be the line: a pick SHALL act on every listed mention on that line (a
`refactor.leftover` with `{where}` `comment`, `docstring`, `string` or `prose`), in source and prose files alike.

- With ENTRY, the pick SHALL rewrite the listed mentions of that entry's old name on the line to that entry's new
  name. Without ENTRY, it SHALL rewrite the listed mentions of every entry's old name on the line, each to its own
  entry's new name.
- Only the characters of OLD SHALL change, and a picked mention SHALL NOT be listed.
- A `patch target` leftover and a `refactor.compound` line SHALL NOT be picked.
- An edit a pick makes at a site `--keep` or `--keep-literal` keeps SHALL be dropped, and the pick SHALL count as
  matched.

Refusals SHALL write nothing and exit 2:
- a pick without `--docs` SHALL print `refactor.pick-needs-docs` in the `checks` phase;
- a pick naming no existing file or line SHALL print `refactor.site-missing` in the `checks` phase;
- a pick whose line holds no listed mention it applies to (with ENTRY: of that entry's old name; an ENTRY that is
  no entry of the map included) SHALL print `refactor.pick-unmatched` naming the pick;
- a pick without ENTRY on a line holding a listed mention of an old name that two entries rename to different names
  SHALL print `refactor.pick-ambiguous` naming the pick, both entries and the old name;
- two picks choosing different entries for one mention SHALL print `refactor.pick-ambiguous` likewise.
Every such refusal of a run SHALL be reported, in the order of the picks.

#### Scenario: A map's module-level mention picked
- **WHEN** a map renames `Table.columns` to `fields` and `Result.columns` to `result_columns`, line 1 of
  `pkg/a.py` is the module docstring holding ``` ``columns`` ```, and the map runs with `--docs --docs-pick
  pkg/a.py:1=1`
- **THEN** line 1 holds ``` ``fields`` ```, no `leftover` is printed for it and the exit code is 0, in both twins

#### Scenario: A bare word picked in a single rename
- **WHEN** `Ds.columns` is renamed to `fields` with `--docs --docs-pick pkg/n.py:10`, where line 10 holds
  `post("/datasets", json={"name": "orders", "columns": ["id"]})`
- **THEN** the key becomes `"fields"` and the line is not listed

#### Scenario: A prose line picked
- **WHEN** a rename runs with `--docs --docs-pick docs/api.md:4`, where line 4 mentions the old name as a plain word
- **THEN** that word is rewritten

#### Scenario: Every mention on the line
- **WHEN** a picked line holds the old name twice as a plain word
- **THEN** both are rewritten

#### Scenario: Two old names on one line
- **WHEN** a map renames `A.x` to `p` and `B.y` to `q`, a comment line mentions both `x` and `y`, and the line is
  picked without ENTRY
- **THEN** `x` becomes `p` and `y` becomes `q`; with `=1` only `x` changes and `y` stays listed

#### Scenario: Ambiguous pick
- **WHEN** the map of the first scenario runs with `--docs --docs-pick pkg/a.py:1`
- **THEN** stderr ends with `refactor.pick-ambiguous` naming `pkg/a.py:1`, entries 1 and 2 and `columns`, the exit
  code is 2 and no file changes

#### Scenario: Two picks disagreeing
- **WHEN** the same map runs with `--docs-pick pkg/a.py:1=1 --docs-pick pkg/a.py:1=2`
- **THEN** stderr ends with `refactor.pick-ambiguous`, the exit code is 2 and no file changes

#### Scenario: Unmatched pick
- **WHEN** a pick names a line with no listed mention, a line whose only mention another rule already rewrote, or
  an ENTRY whose old name the line does not mention
- **THEN** stderr ends with `refactor.pick-unmatched` naming that pick, the exit code is 2 and no file changes

#### Scenario: Pick without --docs
- **WHEN** a rename passes `--docs-pick pkg/a.py:1` without `--docs`
- **THEN** stderr is `[resolve]`, `[checks]` and `refactor.pick-needs-docs`, the exit code is 2 and no file changes

#### Scenario: Missing pick site
- **WHEN** a pick names a file that does not exist or a line past the file's end
- **THEN** stderr holds `refactor.site-missing` naming `--docs-pick` and the site in the `checks` phase, and the
  exit code is 2

#### Scenario: A kept line wins over a pick
- **WHEN** a rename passes `--docs-pick pkg/a.py:7` and `--keep pkg/a.py:7`, where line 7 holds a listed mention
- **THEN** line 7 is unchanged, no `refactor.pick-unmatched` is printed and the exit code is 0

### Requirement: --keep-literal keeps the literals holding a key
`dr-refactor rename` and `rename-map` SHALL accept `--keep-literal KEY` (repeatable, both languages). A matching
literal SHALL be a Python dict display holding a key that is a plain string literal whose source text between its
quotes is exactly KEY, or a TypeScript object literal holding a property named KEY by an identifier, a string
literal or a shorthand property. A computed key, a `**` unpacking and a spread member SHALL NOT make a literal match.

Every edit whose span overlaps a matching literal's span, literals nested in it included, SHALL be dropped, whichever
rule produced it, before any conflict check; a blind spot or a leftover whose span overlaps it SHALL be dropped as
`--keep` drops one, and a blind spot there SHALL NOT block the rename. A literal nested in a matching literal SHALL
be kept with it; a matching literal nested in a literal that does not match SHALL keep only itself.

A `--keep-literal` that dropped no edit and no blind spot SHALL print `refactor.keep-literal-unneeded` naming KEY on
stderr where `refactor.keep-unneeded` is printed, and the run SHALL go on and, with `--apply`, write.

#### Scenario: Versioned document kept
- **WHEN** `Ds.columns` is renamed with `--keep-literal version` and modules hold
  `Ds.model_validate({"version": 3, "columns": ["id"]})` and `Ds.model_validate({"columns": ["id"]})`
- **THEN** the first literal is unchanged, the second's key is renamed and the exit code is 0

#### Scenario: Literal bound to a name
- **WHEN** a function holds `doc = {"version": 3, "columns": []}` followed only by `Ds.model_validate(doc)`
- **THEN** no key of that literal changes

#### Scenario: Nested literals
- **WHEN** `Member.type` is renamed with `--keep-literal version` and modules hold
  `Model.model_validate({"version": 2, "columns": [{"type": "INT"}]})` and
  `Model.model_validate({"columns": [{"version": 1, "type": "INT"}, {"type": "TEXT"}]})`
- **THEN** the first literal is unchanged throughout, and in the second only the member dict without `version` is
  renamed

#### Scenario: Not a matching literal
- **WHEN** literals hold the key `"versions"`, the key `"ver" "sion"`, `**{"version": 3}` or (TypeScript)
  `[key]: 3` with `key = 'version'`, each beside a key the rename rewrites
- **THEN** each is rewritten as without `--keep-literal`

#### Scenario: TypeScript object literal
- **WHEN** property `Ds.columns` is renamed with `--keep-literal version` and a file holds
  `const a: Ds = { version: 3, columns: [] }`, `const b: Ds = { 'version': 3, columns: [] }` and
  `const c: Ds = { columns: [] }`
- **THEN** only `c`'s property is renamed

#### Scenario: Key collision inside a kept literal
- **WHEN** a kept literal holds both `"columns"` and `"fields"` and `Ds.columns` is renamed to `fields`
- **THEN** no `refactor.name-conflict` is printed for it and the rename is written

#### Scenario: Leftover inside a kept literal
- **WHEN** a rename runs with `--docs --keep-literal version` and an untyped `{"version": 3, "columns": []}` would be
  listed as a `leftover`
- **THEN** it is not listed

#### Scenario: Unneeded literal keep
- **WHEN** a rename runs with `--apply --keep-literal schema_version` and no edit and no blind spot of the rename
  overlaps a literal holding that key
- **THEN** stderr holds `refactor.keep-literal-unneeded` naming `schema_version`, the rename is written and the exit
  code is 0

### Requirement: Declared string forms carry a symbol's name
The repo config SHALL accept `refactor.string_forms`: a list of patterns, empty by default. A pattern SHALL be
accepted only when it uses the portable regex subset of the shared contract and holds exactly one capturing group,
the symbol group. Loading a config with any other pattern SHALL fail with a configuration error naming
`refactor.string_forms` and the pattern.

In a rename of a class or of another module-level symbol, with or without `--docs`, in both languages, every string
literal of the language's source files (Python: string literals and f-string literal parts; TypeScript: string
literals and template-literal text) SHALL be searched with every pattern, anywhere in its source text between its
quotes. A match whose symbol group's text is exactly OLD SHALL be a form site. A literal part whose source text
holds a non-ASCII character SHALL hold no form site.

- A form site SHALL be rewritten, only the characters of the symbol group changing, when every module-level
  declaration named OLD in the project is renamed by the run, all to one new name.
- Otherwise it SHALL be unchanged and listed as `refactor.leftover` with `{where}` `string`, with or without
  `--docs`.
- A form site SHALL NOT also be listed as a `--docs` mention, and `--keep`, `--keep-literal` and `--docs-pick` SHALL
  act on it as on any edit or listed mention.

A rename of a member, a parameter, a local or a module SHALL ignore the patterns.

#### Scenario: Cypher labels follow the class
- **WHEN** the config holds `string_forms: ['NODE TABLE (\w+)', '\(\w*:(\w+)\)']`, class `Model` is renamed to
  `Dataset` without `--docs`, and a module holds `"CREATE NODE TABLE Model(name STRING, PRIMARY KEY(name))"` and
  `"MATCH (m:Model) RETURN m.name"`
- **THEN** both strings name `Dataset`, nothing else in them changes, nothing is listed and the exit code is 0, in
  both twins

#### Scenario: f-string and template text
- **WHEN** the same rename runs and a module holds `f"MATCH (m:Model) WHERE m.id = {i}"` (Python) or
  `` `MATCH (m:Model) WHERE m.id = ${i}` `` (TypeScript)
- **THEN** the label becomes `Dataset`

#### Scenario: Another symbol in the form
- **WHEN** the same rename runs and a module holds `"MATCH (m:ModelColumn)"` and `"a Model in prose"`
- **THEN** neither string changes; neither is listed without `--docs`, and with `--docs` only the second is

#### Scenario: Simple-name collision listed
- **WHEN** another module also declares a class `Model` that the run does not rename
- **THEN** every form site is unchanged and listed as `leftover` with `{where}` `string`, with and without `--docs`

#### Scenario: Collision resolved by a pick
- **WHEN** the same rename runs with `--docs --docs-pick pkg/g.py:5`, where line 5 holds a listed form site
- **THEN** that site is rewritten

#### Scenario: Escapes are not decoded
- **WHEN** a module holds `"MATCH (m:\x4dodel)"`
- **THEN** it is unchanged and holds no form site

#### Scenario: Non-ASCII literal
- **WHEN** a module holds `"MATCH (m:Model) // modèle"`
- **THEN** it holds no form site; with `--docs` its `Model` is listed as a `leftover`

#### Scenario: Member rename ignores the forms
- **WHEN** field `Model.name` is renamed and a module holds `"MATCH (m:name)"`
- **THEN** that string is unchanged, and without `--docs` unlisted

#### Scenario: Invalid pattern
- **WHEN** the config holds a pattern with no capturing group, with two, with a named group or with a lookahead
- **THEN** every command loading the config fails with a configuration error naming `refactor.string_forms` and
  that pattern, and the exit code is 2
