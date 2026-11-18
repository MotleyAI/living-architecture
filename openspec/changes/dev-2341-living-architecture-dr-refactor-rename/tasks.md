## 1. Shared contract

- [ ] 1.1 Add `string-blindspot` to `compliance_checks` of both languages in `shared/languages.yaml`, the `silent` /
  `default` facts on `hasattr` / `getattr`, and the `name_decorators`, `name_reads` and `name_class_values` entries
  (design decision 1), with the header comment describing each key; verify the contract tests of both twins load them
- [ ] 1.2 Add `compliance.string-blindspot`, `compliance.string-blindspot-silent` and `refactor.unverified-read` to
  `shared/findings.yaml` and change `compliance.attr-required` and `compliance.attr-unselected`, all exactly as
  design decision 4 quotes them; verify by diffing against that block
- [ ] 1.3 Reword the `--attr` help in `shared/cli.yaml` to name both attribute checks; verify `dr-compliance --help`
  in both twins
- [ ] 1.4 Run `scripts/sync-shared`; verify `scripts/sync-shared --check` is clean
- [ ] 1.5 Each twin validates the new registry keys on load; verify with a structural test per twin that a malformed
  entry is a contract error

## 2. Conformance cases (written failing, listed in `conformance/INVENTORY.md`)

Fixtures come from the issue's repro projects (`repros/item-3`, `item-3b`, `item-4`, `item-5`, `repro21`); each case
below is one spec scenario unless it says several.

- [ ] 2.1 Adapter (python), field-name strings: validator on the declaring class; on a subclass; several names and
  `"*"`; serializer; aliased import and lookalike; the five `model_fields` / `model_fields_set` reads; another
  model's fields; aliased field; base without the field; union with an unrenamed model; decorator already holding
  NEW. Verify each fails on `main`
- [ ] 2.2 Adapter (python), class-body values: slots tuple; single string, list and dict slots; inherited
  `__match_args__`; a class passed to `--without`; computed value; value already holding NEW
- [ ] 2.3 Adapter (python), module receivers: `monkeypatch.setattr` and `patch.object` on an imported module, with
  and without `--docs`; alias and dotted receiver; re-exporting package; same name in another module; module found
  twice; object that is not a module
- [ ] 2.4 Paired, names followed in a member rename: constant tuple; only the matching element; direct display and
  single constant; chain and import; use on an unrenamed class (`mixed-target`); only an unrenamed class; names
  without sources (one function per unsupported binding); display already holding NEW. Python-only: field-name read
  through a name. TypeScript-only: array without `as const`
- [ ] 2.5 Paired, literal-member rename: module constant; local; class constant and loop; value with two sources;
  twice-bound local and twice-bound module constant (the two retitled scenarios, design decision 22); source also
  typed by another literal type; source in a stub (`.pyi` / `.d.ts`). TypeScript-only: an error present before the
  rename is not a blind spot
- [ ] 2.6 Paired, `unverified-read`: tuple also used as a key; second reader in another module; literal constant
  with an untyped read; nothing rewritten, nothing listed (unrenamed class, and `--keep` on the source line)
- [ ] 2.7 Paired, `string-blindspot`: call forms on an untyped object; the element access (typescript); multiline
  receiver; `--select string-blindspot`, `--select attr-blindspot`, no `--select`; `--select string-blindspot`
  without `--attr`. Adapter (python): `hasattr` and `getattr` with a default (silent variant); a field-name read on
  an untyped receiver; the rename of `Ds.columns` with `--allow-blindspots` printing both kinds
- [ ] 2.8 Existing cases whose fixture or golden this plan changes: `refactor-literal-narrowed-local` and
  `refactor-literal-import-routes-blindspot` get the twice-bound fixtures; every golden that prints a string form
  as `attr-blindspot` gets the new kind and site. List each changed case in the commit message with its reason

## 3. Unit tests

- [ ] 3.1 Python: the literal-source resolver, one test per supported binding and per unsupported one (design
  decision 15), chains, imports, sources outside the project
- [ ] 3.2 TypeScript: the same for `const`, once-assigned `let`, static readonly members, `for…of`, array-method
  callbacks and `as const` arrays
- [ ] 3.3 Per twin: `{site}` rendering for each form kind, including collapsed whitespace and the `, …` rule
- [ ] 3.4 Python: decorator, read and class-body forms matched by resolved declaration, not spelling

## 4. Python implementation

- [ ] 4.1 Literal-source resolver on the existing static resolver and scope helpers; verify 3.1
- [ ] 4.2 Form scan reads the new registry entries: decorators, reads, class-body values, with lookup through the
  keyed-class method resolution order; verify 2.1 and 2.2
- [ ] 4.3 Module receivers through the dotted-target resolver; verify 2.3
- [ ] 4.4 Member rename follows names to their sources, with `mixed-target` and `name-conflict`; verify 2.4
- [ ] 4.5 Literal-member rename rewrites sources and repeats the probe; verify 2.5
- [ ] 4.6 `unverified-read` listing; verify 2.6
- [ ] 4.7 `string-blindspot` check and kinds in `dr-compliance` and in the rename's blind spots, from the one scan;
  verify 2.7 and that the rename and `--attr` report the same positions and kinds

## 5. TypeScript implementation

- [ ] 5.1 Literal-source resolver on the checker's symbols and write references; verify 3.2
- [ ] 5.2 In-memory check of the edited program with before/after comparison and position mapping; new errors become
  `literal-unresolved`; verify 2.5
- [ ] 5.3 Member rename follows names for string-member forms and `d[s]`; verify 2.4
- [ ] 5.4 `unverified-read` listing; verify 2.6
- [ ] 5.5 `string-blindspot` check, element access included; verify 2.7

## 6. Docs, versions and gates

- [ ] 6.1 Update `docs/deterministic-refactoring.md` and the plugin skills that name `attr-blindspot` for string
  forms or describe `literal-unresolved`; skill wording needs the user's OK before it is edited
- [ ] 6.2 Raise the minor version in `python/pyproject.toml`, `node/package.json` and
  `plugin/.claude-plugin/plugin.json`; verify the version test and that every `CONTRACT_HASH` equals the hash of
  `shared/`
- [ ] 6.3 Run the local test scope of both twins, `scripts/conformance-cross`, lint and type checks of both twins,
  and the enforcement bundle (`la-arch-check`, `npx likec4 validate`, `la-typecheck`); verify all are green
