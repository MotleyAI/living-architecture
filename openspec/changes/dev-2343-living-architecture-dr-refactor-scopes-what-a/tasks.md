## 1. Shared contract

- [ ] 1.1 Get the user's OK on the exact wording still open in design.md ("Approved wording": the two flag help
  texts, the `refactor.string_forms` schema description, the `shared/regex-subset.md` edit); record each approved text
  there before writing it
- [ ] 1.2 `shared/cli.yaml`: `--docs-pick` (`PATH:LINE[=ENTRY]`, repeatable) and `--keep-literal` (`KEY`, repeatable)
  on `rename` and `rename-map`; verify both twins' `--help` list them
- [ ] 1.3 `shared/findings.yaml`: `refactor.pick-needs-docs`, `refactor.pick-unmatched`, `refactor.pick-ambiguous`,
  `refactor.keep-literal-unneeded`, with the approved texts of design.md
- [ ] 1.4 `shared/schema/living-architecture.schema.json` and `shared/config.yaml`: `refactor.string_forms` (list of
  strings, default empty); `shared/regex-subset.md` names the key; verify `la-config show` prints the default
- [ ] 1.5 `scripts/sync-shared`; verify `scripts/sync-shared --check` passes

## 2. Tests first (pr-tests)

- [ ] 2.1 Python unit tests (`python/tests/test_rename_docs.py` and beside it): the owning class of a mention
  (decorated class, nested class, class without the member, inherited member, unresolved base); the file-level rule;
  one resolution for two entries sharing an old name; no string-opening mark; pick parsing and each refusal;
  literal-keep span matching (nested, non-matching forms, overlap); form sites on raw text (escapes, non-ASCII,
  f-string parts); config load of `refactor.string_forms` (valid, zero groups, two groups, named group, lookahead)
- [ ] 2.2 Node unit tests (`node/test/rename-outcomes.test.ts`, `rename-map.test.ts`, `config.test.ts` and beside
  them): the same list for TypeScript (JSDoc attached to a class, interface and type literal; a detached comment
  before a class is not owned; merged interface declarations; object-literal keys by identifier, string and
  shorthand, not computed or spread; template-literal text)
- [ ] 2.3 Conformance, paired Python and TypeScript, `golden: manual`: `refactor-docs-owning-class` (item 22: another
  class's docstring or JSDoc listed, the plain word in a message string listed), `refactor-docs-module-level`
  (listed beside an unrenamed declaration, rewritten with one), `refactor-docs-inherited-member`,
  `refactor-map-docs-owning-class` (item 9 with each class's own docstring), `refactor-map-docs-listed` (item 9: the
  module-level mention listed once, exit 0, no `map-conflict`, identical in both twins)
- [ ] 2.4 Conformance for `--docs-pick`: `refactor-docs-pick-map` (paired; item 9 resolved with `=1`),
  `refactor-docs-pick-bare` (the untyped body of item 10 and a prose line), `refactor-docs-pick-two-names`,
  `refactor-docs-pick-ambiguous` (produces `refactor.pick-ambiguous`; also two disagreeing picks),
  `refactor-docs-pick-unmatched` (produces `refactor.pick-unmatched`), `refactor-docs-pick-needs-docs` (produces
  `refactor.pick-needs-docs`), `refactor-docs-pick-missing` (`refactor.site-missing`), `refactor-docs-pick-kept`
- [ ] 2.5 Conformance for `--keep-literal`: `refactor-keep-literal` (Python adapter; item 10's versioned document, a
  literal bound to a name, nested literals, the non-matching forms), `refactor-keep-literal-typescript` (adapter),
  `refactor-keep-literal-collision` (no `name-conflict` inside a kept literal), `refactor-keep-literal-leftover`,
  `refactor-keep-literal-unneeded` (paired; produces `refactor.keep-literal-unneeded`)
- [ ] 2.6 Conformance for string forms: `refactor-string-forms` (paired; item 12 without `--docs`, f-string and
  template text, another symbol in the form), `refactor-string-forms-collision` (listed with and without `--docs`,
  and resolved by a pick), `refactor-string-forms-raw` (escape and non-ASCII), `refactor-string-forms-member`,
  `config-string-forms-invalid` (neutral; the configuration error)
- [ ] 2.7 Existing tests and goldens that pin the old shape: list each file and what changes in it (the
  string-opening rewrite in `refactor-rename-docs` and its unit tests; any docs `map-conflict`), and get the user's
  approval per file before editing, as the `/la:pr` stopping policy requires
- [ ] 2.8 List every new case in `conformance/INVENTORY.md`; verify every new `findings.yaml` template is produced by
  a golden

## 3. Python twin

- [ ] 3.1 `mentions`: drop the string-opening mark; class spans and the owner resolution; verify 2.1's mention tests
- [ ] 3.2 `rename_union` / `rename_map`: one mention resolution per old name over the entries sharing it, so no docs
  edit reaches `merged` twice; verify `refactor-map-docs-*`
- [ ] 3.3 `--docs-pick`: parsing, the `checks`-phase refusals, resolution over the final listed mentions beside the
  keeps; verify `refactor-docs-pick-*`
- [ ] 3.4 `--keep-literal`: matching dict displays, overlap filtering of edits, blind spots and leftovers before the
  conflict phase, the unneeded warning; verify `refactor-keep-literal*`
- [ ] 3.5 Config: load and validate `refactor.string_forms` (regex subset, one capturing group); the string-form rule
  for class and module-level symbol renames, its sites excluded from the `--docs` scan; verify
  `refactor-string-forms*` and `config-string-forms-invalid`

## 4. npm twin

- [ ] 4.1 `mentions.ts`: drop the string-opening mark; class spans with attached JSDoc and the owner resolution;
  verify 2.2's mention tests
- [ ] 4.2 `rename.ts`: one mention resolution per old-name group replacing the single-new-name shortcut; verify
  `refactor-map-docs-*`
- [ ] 4.3 `--docs-pick`, as 3.3; verify `refactor-docs-pick-*`
- [ ] 4.4 `--keep-literal` on object literals, as 3.4; verify `refactor-keep-literal*`
- [ ] 4.5 Config and the string-form rule, as 3.5; verify `refactor-string-forms*`

## 5. Docs, skill, versions

- [ ] 5.1 `docs/deterministic-refactoring.md`, `docs/configuration.md`, `docs/refactoring-internals.md`: the new
  scoping, flags and config key
- [ ] 5.2 `plugin/skills/deterministic-refactor/SKILL.md`: show the user the exact wording and get the OK before
  editing; then verify `npx -y @anthropic-ai/claude-code plugin validate plugin`
- [ ] 5.3 Minor version bump of `python/pyproject.toml`, `node/package.json` and `plugin/.claude-plugin/plugin.json`
  together (0.11.0 to 0.12.0), lockfiles included; reinstall the local editable `la` tools from the checkout
- [ ] 5.4 Record on DEV-2343 that untyped document bodies were declined, with the reason of design.md decision 7

## 6. Gates

- [ ] 6.1 `scripts/conformance-cross` passes for the changed cases through both twins
- [ ] 6.2 The enforcement bundle: `la-arch-check`, `npx likec4 validate`, `la-typecheck`; lint and type-check of both
  twins
