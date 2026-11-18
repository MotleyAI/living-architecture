## Context

See proposal.md for the motivation. Facts that shape the approach:

- A rename map is a flat list of entries, each resolved to one symbol; `rename` is a one-entry map. Symbol paths
  are resolved from syntax in both twins (`symbol_path.py`, `symbols.ts`) without the checker.
- A stand-in is any class outside the renamed hierarchy that declares a member of the old name. Each needs `--with`
  or `--without`. A class that is its own map entry is not a stand-in: verified on 0.11.0 with the DEV-2340 item-6
  project and a third entry `{file: pkg/q.py, symbol: Fake.root_model, new_name: population}` (exit 0, clean diff).
- `--docs` rewrites only qualified mentions and code-marked bare mentions in a declaring file. Everything else is
  already listed.
- Names are split into words by the compound-name rule (`compound.py` `words`, `compound.ts`).
- Probed on 0.11.0: `rename --symbol load_model` on `from pkg.a import load as load_model` renames the alias only.
  `rename --symbol model_mod` on `import pkg.a as model_mod` moves `pkg/a.py` to the alias's new name and leaves
  `import pkg.a`, so the import breaks. A locator at a comprehension target renames it; a lambda parameter is
  refused (`the element at this location cannot be renamed`).

Architecture principles that apply (`architecture/system.arc42.md`): 1 (twins: every observable behaviour identical,
decided by the conformance corpus), 2 (flags, texts and the fixture decorators come only from `shared/`), 3 (the
language-specific indexing and annotation reading live in `refactor`), 4 (the generator reads files and never
imports or runs project code). No model or arc42 edit is needed: no new element or arrow, and the requirements join
the `refactor` spec that `python.refactor` owns.

## Goals / Non-Goals

**Goals:**

- One word table drives the generator, the stand-in defaults and the `--docs` sense rules, so they cannot disagree.
- The generator is syntactic: no checker, deterministic output, cheap to re-run.
- A generated map is the input of an unchanged `rename-map`; the dry run stays the one place where renames are
  validated and refused.

**Non-Goals:**

- The re-check after a map change (DEV-2340 item 8). Deferred until after DEV-2323; the hand-over note is a comment
  on DEV-2323.
- `--with PATH:LINE=NAME`. Declined: a map entry already gives a stand-in its own name.
- A phrase matcher for prose, and any rewriting of plain-word prose from the table.
- Inferring inflections, and classifying unannotated declarations by type.
- A preflight in the generator for name conflicts, keywords or captures: `rename-map` reports these.
- `--docs` scoping by owning class and the per-site pick (DEV-2343); refusal reporting defects (DEV-2344).

## Decisions

1. **The re-check is not built here.** Options: build all five features; build four and defer the re-check. Taken:
   defer. It persists per-entry results held in the structures DEV-2323 reshapes, and the TypeScript twin has no
   persisted state. (user)
2. **Carve-outs are structural: `annotated`, `paths`, `symbols`. No phrase matcher.** A phrase rule only pays off
   with plain-word prose rewriting, which the issue does not ask for. (user)
3. **One word table, passed to the rename as `--words TABLE`.** Options: bake the carve-outs into the map; a config
   key in `living-architecture.yaml`; an option naming the table. Taken: the option. A carve-out belongs to one
   rename, not to the repo, and the map schema stays a flat list. (default)
4. **`--with PATH:LINE=NAME` is declined.** A stand-in that is its own map entry already gets its own name, and the
   generator writes that entry. (user)
5. **The generator writes module entries in both languages.** (user)
6. **`entries` in the word table.** Hand-written map entries are written first and replace the generated entry for
   the declaration they locate, so a hand decision survives regeneration. An entry also overrides a carve-out.
   (user)
7. **Every matcher gives the `--without` default**, not only `paths`: a carved member is left out of the map and
   would otherwise be a stand-in. (user)
8. **Inflections are not inferred; one lowercase word per side; case is carried over.** (user)
9. **`annotated` reads written annotations only**, on parameters, variables and fields. (user)
10. **The generator writes same-named locals of a file as one wildcard entry** when none is carved or in `entries`.
    Options: always one entry per local; the wildcard. Taken: the wildcard; the size of the locals map is the pain
    the issue names. (default)
11. **The fixture default is always on and is a language fact** (`fixture_decorators` in `languages.yaml`), not a
    flag. An explicit `--with` overrides it. (default)
12. **`--words` is taken by `rename`, `rename-map` and `retarget`**, since `rename` and `retarget` are one-entry
    maps and must print what the map prints. (default)
13. **A carved `--docs` mention reuses `refactor.leftover`.** (default)
14. **`generate-map` picks its language from the project, `--language` when it holds both.** Its input is a table,
    not a source file, so file-language routing has nothing to route by. (default)
15. **A locator on a module's `as` alias renames the alias only.** Options: fix here; leave it and have the
    generator skip module aliases. Taken: fix here. The current behaviour breaks the import, and the generator
    emits this entry. No existing issue covered it (searched Linear: "import alias module rename",
    "living-architecture dr-refactor alias"). (user)
16. **A wildcard entry expands at resolve into one internal target per located symbol**, all sharing the entry's
    index, header and progress item; duplicates and merges are decided per expanded symbol. (codex)
17. **`*` is matched over function paths**: `*.<locals>.NAME` is every function of the file, `P.*.<locals>.NAME`
    every function nested at any depth in P. (codex)
18. **A candidate is written by path only when the path locates exactly its symbol, else by line and column.**
    (codex)
19. **`entries` are validated and resolved before generation**; another language's entry is refused. (codex)
20. **Fixture default**: only class-member functions can be stand-ins; the default classifies through the same
    hierarchy step as `--without`; `--without` on a defaulted stand-in is accepted; precedence is `--with`, then
    `--without`, then the default. (codex)
21. **A default applies only when every member declaration of the stand-in's hierarchy qualifies.** Options: any
    declaration; every declaration. Taken: every; a partly covered hierarchy is reported as today. (codex)
22. **Scopes for carved mentions are exact source spans**: module is the file; a class or function runs from its
    first decorator (TypeScript: its attached JSDoc) to its end; a comment before it is outside. (codex)
23. **A `symbols` or `annotated` carve-out covers a mention only for a declaration whose whole name is OLD.** (codex)
24. **Annotation matching is identifier-token equality on the annotation's text**, string annotations included,
    with no resolution; listed names are single identifiers. (codex)
25. **Module candidates**: one per module file and per package (by its `__init__.py`); `__init__` itself and
    directories without one are never candidates. (codex)
26. **`generate-empty` is decided on the final map**, `entries` included. (codex)
27. **Conformance covers both invoking twins** for the invalid table, `--language`, and a relative TABLE with
    `--project`. (codex)
28. **Every changed existing requirement is a MODIFIED requirement** in the delta: routing, locators, stand-ins,
    `--docs`, symbol paths, rename maps. (codex)
29. **Word-replacement vectors cover case forms, acronym runs and non-ASCII names.** (codex)
30. rejected (codex): **a generator preflight** that resolves candidates with the map resolver and reports name
    conflicts, keywords and colliding generated names. The generator is syntactic by design; the `rename-map` dry
    run already reports every refusal of a map in one report, and the fix for each is a carve-out or an entry.
31. rejected (codex): **a finding explaining each line/column fallback.** The entry shows its own locator.
32. rejected (codex): **applying the duplicate-intent rule between an `entries` item and a generated entry.**
    Replacing the generated entry is what `entries` is for.
33. rejected (codex): **aggregating locals only after a per-local preflight.** Same reason as 30; same-named locals
    always get the same new name.

### Approved wording

`shared/findings.yaml` (user, approved wording):

```yaml
refactor.words-invalid: '{table}: {section} item {index} is not valid'
refactor.carved: '{path}:{line}: carve-out: {name} keeps {word} ({matcher})'
refactor.not-generated: '{path}:{line}: not-generated: {name} spells {word}, but no map entry can rename it'
refactor.generate-empty: '{table}: no declaration in the project spells a word of the table'
refactor.generate-language: 'the project holds sources of more than one language ({languages}); pass --language'
refactor.symbol-wildcard: '{path}: {symbol} names every matching local, which only a rename takes'
```

`{section}` is `words`, `carve_outs` or `entries`. `{matcher}` is the matcher's key and the value that matched:
`annotated IntrospectedColumn`, `paths pkg/sql/**`, or `symbols`.

`shared/cli.yaml` (user, approved wording):

```yaml
generate-map:
  help: >-
    write a rename map for a word table: one entry per declaration and module whose name holds a word,
    leaving out and listing what a carve-out matches
  positionals:
    - {name: table, help: 'the word table: words {from, to}, carve_outs {words, annotated | paths | symbols} and entries'}
  options:
    - {name: --language, type: string, choices: [python, typescript],
       help: 'the language to generate for (required when the project holds both)'}

# on rename, rename-map and retarget
- {name: --words, type: path, metavar: TABLE,
   help: "a word table whose carve-outs leave matching stand-ins and list matching --docs mentions"}
```

The `--symbol` help on `rename` gains one form at the end of its list: `'*.<locals>.name'` (every local of that
name). (user, approved wording)

`plugin/skills/deterministic-refactor/SKILL.md`, step 4, the `stand-in` bullet (user, approved wording):

```
   - `stand-in`: a class outside the hierarchy declares `OLD`. `--with PATH:LINE` renames it too
     (a duck-typed implementation: a cache, a fake, a `cast()` target); `--without PATH:LINE` leaves it
     (an unrelated class). To give it a different new name, add it to the map as its own entry.
     Pytest fixtures are left by default.
```

The same file, Commands section, a new paragraph after the existing one (user, approved wording):

```
A vocabulary rename (one word replaced across the repo) starts from a word table.
`dr-refactor --project <repo> generate-map TABLE > MAP` writes one entry per declaration and
module whose name holds a word (`words: [{from, to}]`, one row per inflection). `carve_outs`
(`{words, annotated | paths | symbols}`) leave out a declaration where the word keeps its old sense, and
`entries` holds hand-written map entries, kept on every regeneration. Change the table and regenerate;
never edit MAP by hand. Pass the table to the rename as `--words TABLE`: carved stand-ins are left and
carved `--docs` mentions are listed as `leftover`. A map entry
`{file, symbol: '*.<locals>.NAME', new_name}` renames every local of that name in the file.
```

## Risks / Trade-offs

- [A generated map can be refused by `rename-map` (a new name already bound, a keyword, two names converging)] →
  The dry run reports every refusal in one report; each is fixed in the table by a carve-out or an entry, then
  regenerated.
- [The stand-in and `refactor.map-conflict` paths differ between the twins when two entries rename one member name
  differently (DEV-2344)] → Stand-in cases of this change use entries with one new name, or classify by entry, so no
  golden depends on that difference.
- [A Python namespace package whose name holds a word is not renamed] → Namespace-package directories are not
  candidates and are found by the compound-name listing of `--docs` only if a declaration spells the word. Stated in
  `docs/deterministic-refactoring.md`.
- [The alias fix changes existing behaviour] → Only for a locator on the `as` name of a project module's import,
  which produced broken code. A golden that pins the old output is aligned only with the user's approval of that
  file (the `/la:pr` stopping policy).
- [`annotated` matches by text, so an unrelated type of the same simple name also matches] → Accepted: the carve-out
  is listed on stderr for review, and `entries` overrides it.
