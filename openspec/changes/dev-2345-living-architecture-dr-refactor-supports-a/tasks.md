## 1. Shared contract

- [ ] 1.1 `shared/schema/word-table.schema.json`: `words`, `carve_outs` (exactly one matcher), `entries` (items are
  rename-map entries); verify with schema unit tests in both twins (valid table, each invalid form)
- [ ] 1.2 `shared/findings.yaml`: the seven findings, texts verbatim from design.md "Approved wording"; verify each is
  produced by at least one golden
- [ ] 1.3 `shared/cli.yaml`: the `generate-map` subcommand, `--words` on `rename`, `rename-map` and `retarget`, the
  `--symbol` help form, the `dr-refactor` help's subcommand list, texts verbatim from design.md; verify with the CLI
  vectors
- [ ] 1.4 `shared/languages.yaml`: `fixture_decorators` (`pytest.fixture`, `pytest_asyncio.fixture` for Python, empty
  for TypeScript); verify it is read through the contract in both twins
- [ ] 1.5 `shared/vectors/refactor-words.yaml`: name plus table gives new name and held words (case forms, acronym
  runs, non-ASCII names, whole words only, no second replacement); verify both twins run it
- [ ] 1.6 `scripts/sync-shared`; verify `scripts/sync-shared --check` passes

## 2. Tests first (pr-tests)

- [ ] 2.1 Python unit tests: word replacement (the vectors); table loading and every invalid form with its section
  and index; annotation token matching (subscripts, unions, dotted names, string annotations, none); wildcard
  location (file-wide, class-scoped, nested functions, parameters excluded, no match, misplaced `*`); candidate
  indexing (path round trip, line/column fallback, lambda parameter, `as` aliases, modules and packages)
- [ ] 2.2 Node unit tests: the same list for TypeScript (JSDoc span, arrow functions and function expressions as
  wildcard scopes, module files listed)
- [ ] 2.3 Conformance, generator (paired unless noted): `refactor-generate-words` (DEV-2340 item 1, and `rename-map`
  on the output), `refactor-generate-annotated` (item 14), `refactor-generate-paths-symbols`,
  `refactor-generate-partial-word`, `refactor-generate-entries`, `refactor-generate-entry-over-carve`,
  `refactor-generate-locals-wildcard`, `refactor-generate-locals-split`, `refactor-generate-modules` (Python adapter),
  `refactor-generate-modules-ts` (TypeScript adapter, produces `refactor.not-generated-module`),
  `refactor-generate-lambda` (Python adapter, produces `refactor.not-generated`), `refactor-generate-ambiguous`,
  `refactor-generate-hierarchy`, `refactor-generate-empty`, `refactor-generate-entries-only`,
  `refactor-generate-no-write` (with `--apply`, git status clean)
- [ ] 2.4 Conformance, neutral through both invoking twins: `refactor-words-invalid`, `refactor-words-unreadable`,
  `refactor-generate-language` (mixed project, with and without `--language`), `refactor-generate-relative-table`
  (TABLE and `--project` given from a subdirectory), `refactor-generate-entries-other-language`
- [ ] 2.5 Conformance, wildcard (paired): `refactor-wildcard-locals` (item 2), `refactor-wildcard-class`,
  `refactor-wildcard-no-match`, `refactor-wildcard-refused` (retarget, retarget entry, move-symbol, carve-out symbol),
  `refactor-wildcard-merge`, `refactor-wildcard-duplicate`, `refactor-wildcard-conflict`,
  `refactor-wildcard-single-rename` (`rename --symbol`)
- [ ] 2.6 Conformance, stand-in defaults: `refactor-stand-in-fixture` (item 6, Python adapter),
  `refactor-stand-in-fixture-alias`, `refactor-stand-in-fixture-with`, `refactor-stand-in-fixture-without`,
  `refactor-stand-in-fixture-partial`, `refactor-stand-in-carved-path` (paired, with and without `--words`),
  `refactor-stand-in-carved-annotated` (paired)
- [ ] 2.7 Conformance, carved mentions (paired unless noted): `refactor-docs-carved-path`,
  `refactor-docs-carved-annotated` (with the comment before the function), `refactor-docs-carved-symbols`,
  `refactor-docs-carved-qualified`, `refactor-docs-carved-jsdoc` (TypeScript adapter)
- [ ] 2.8 Conformance, alias locator (Python adapter): `refactor-rename-module-alias` (`import x.y as NAME`, with
  `--apply`), `refactor-rename-module-alias-from` (`from x import y as NAME`), `refactor-rename-module-alias-stub`
- [ ] 2.9 Search `conformance/cases/` and both twins' tests for a test that pins the old output of a locator on a
  project module's `as` alias; for each one found, ask the user to approve aligning that file, naming the file and
  the change, before editing it
- [ ] 2.10 List every new case in `conformance/INVENTORY.md`; verify the inventory test passes

## 3. Python twin

- [ ] 3.1 Word table: load, validate, report invalid items; word replacement on the compound-name split; verify 2.1
- [ ] 3.2 Carve-out matchers over syntax (annotation tokens, path globs, symbol locators); verify 2.1
- [ ] 3.3 `generate-map`: candidate index over the project's sources, modules and packages, `entries` first, locals
  aggregation, YAML output, listings; language selection and forwarding; verify 2.3 and 2.4
- [ ] 3.4 Wildcard paths in `symbol_path`; one map entry expanding to several internal targets under one index
  (headers, progress, findings, duplicates and merges per symbol); the refusals; verify 2.5
- [ ] 3.5 Stand-in defaults in classification: fixture decorators resolved through imports, carve-outs with
  `--words`, the every-declaration rule, `--with` and `--without` on a defaulted stand-in; verify 2.6
- [ ] 3.6 Carved mentions: scope spans, covering rule, listed as `refactor.leftover`; verify 2.7
- [ ] 3.7 Entry location: a locator on the `as` name of a module import is the alias binding; `--stub` refusal as for
  a library alias; verify 2.8

## 4. npm twin

- [ ] 4.1 Word table, replacement and matchers (type-annotation identifier tokens); verify 2.2
- [ ] 4.2 `generate-map` for TypeScript: candidates from the TypeScript syntax tree, module files listed, `entries`,
  locals aggregation, output; language selection and forwarding; verify 2.3 and 2.4
- [ ] 4.3 Wildcard paths in `symbols.ts` and multi-target entries in the map run; the refusals; verify 2.5
- [ ] 4.4 Carve-out stand-in default (the fixture list is empty) and carved mentions with the JSDoc span; verify 2.6
  and 2.7

## 5. Docs and skill

- [ ] 5.1 `plugin/skills/deterministic-refactor/SKILL.md`: the two edits, verbatim from design.md "Approved wording";
  verify `npx -y @anthropic-ai/claude-code plugin validate plugin` passes
- [ ] 5.2 `docs/deterministic-refactoring.md`: the vocabulary-rename flow (table, generate, dry run with `--words`,
  regenerate), the stand-in-as-entry route, the fixture default, what is not generated (lambda parameters,
  TypeScript modules, namespace packages); `docs/commands.md`: `generate-map`
- [ ] 5.3 `dr-refactor` help in `cli.yaml` and the docs name `generate-map` wherever the subcommands are listed;
  verify by reading each list

## 6. Gates

- [ ] 6.1 The local test scope passes in both twins (`la-affected-tests --base main`, plus every new conformance case
  through `scripts/conformance-cross`)
- [ ] 6.2 `uv run ruff check src tests` and `uv run basedpyright src tests` in `python/`; `npm run lint && npm run
  typecheck` in `node/`
- [ ] 6.3 The enforcement bundle: `la-arch-check`, LikeC4 model validation, `la-typecheck`; no model or arc42 change
  is expected, and any that turns out to be needed is presented to the user for approval first
