## 0. Stage order (read first)

- [x] 0.1 pr-tests: write the failing tests for every scenario of this change's delta specs (unit tests in both
      twins; conformance cases per design decision 37, listed in `conformance/INVENTORY.md`), then a Codex review of
      the tests against the plan. This branch already holds DEV-2292's failing tests, so `/la:pr` stage detection
      picks `pr-implement`: run this stage by naming `pr-tests` when invoking `/la:pr`. DEV-2292's tests stay
      failing alongside; do not touch them.
- [ ] 0.2 Precondition for pr-implement: DEV-2292's implementation is merged into this branch (merge its branch, or
      `origin/main` once it has landed), and DEV-2292's tests pass here. Do not start section 1 before that.

## 1. Shared contract

- [ ] 1.1 `shared/cli.yaml`: `--symbol` on `rename` and `move-symbol`, `--name` removed; an `exclusive` group
      `[offset, line, symbol]` on both, and the manifest header comment documents `exclusive`; subcommand `rename-map`
      (positional `map`, `rename`'s options minus the locator and `--new-name`); subcommand `retarget` (`--file`,
      the locators, `--target`, `--allow-blindspots`, `--with`, `--without`, `--keep`, `--docs`); `--attr`
      `repeatable: true` on `dr-compliance`; `dr-mock-lint` not `passthrough`, with positional `paths` (`+`) and
      `--base`. Verify with both twins' CLI vector and manifest tests.
- [ ] 1.2 `shared/findings.yaml`: `refactor.symbol-unresolved`, `refactor.symbol-ambiguous`, `refactor.map-invalid`,
      `refactor.map-mixed-languages`, `refactor.map-duplicate`, `refactor.map-conflict`, `refactor.retarget-header`,
      `refactor.retarget-scope`, `refactor.retarget-override`, `refactor.retarget-shadowed`,
      `refactor.write-failed`, `refactor.baseline-ambiguous`, `refactor.baseline-failed`, `refactor.literal-value`,
      `refactor.literal-unresolved`, `refactor.compound`; drop templates only `--name` used. Verify every new
      template is produced by a golden (task 10.3).
- [ ] 1.3 `shared/schema/rename-map.schema.json` (decision 13). Verify with schema unit tests in both twins (valid
      entries, both intents, two locators, unknown key).
- [ ] 1.4 `scripts/sync-shared`; verify `scripts/sync-shared --check` and the drift tests pass.

## 2. CLI manifest `exclusive` (both twins)

- [ ] 2.1 Both parser builders reject more than one option of an `exclusive` group with exit 2. Verify with the
      "Exclusive options rejected together" scenario through both twins.

## 3. Symbol paths (both twins)

- [ ] 3.1 Python: parse Q, walk the module AST (module, class, `self.NAME`, `<locals>`, `(param)`, `['value']`),
      group declarations by checker symbol (decision 32), candidates on failure, exit 2. Verify with the "Symbols are
      located by their path in a file" scenarios and one test per grouping construct.
- [ ] 3.2 TypeScript: the same over the TypeScript AST and checker symbols (members, enums, namespaces, type
      literals through aliases, locals, parameters, `['value']`). Verify with Vitest and "TypeScript member and
      local by path".
- [ ] 3.3 Remove `--name` from both twins; migrate every conformance case using it to `--symbol` (the goldens are
      unchanged except where a case pinned `--name`'s guess, e.g. `refactor-ts-rename-name-prefers-declaration`,
      `refactor-ts-symbol-not-found`, which change to the new findings). Verify with `scripts/conformance-cross`.

## 4. Map engine (both twins)

- [ ] 4.1 Python: load and validate MAP; one language; resolve every locator first; canonicalise symbols
      (decision 31); one snapshot, one language server, each rename rule once over the union; one blind-spot scan
      for every member entry's old name; merge edits, `refactor.map-conflict`; `rename` routed through it. Verify
      with the "Rename maps apply many renames as one" scenarios and "Single rename equals its map".
- [ ] 4.2 TypeScript: the same over one workspace session. Verify with Vitest.
- [ ] 4.3 Routing: `rename-map` routes by its entries' files, forwarding raw argv to the other twin. Verify with
      "TypeScript map through the PyPI twin".
- [ ] 4.4 Writer (both twins): re-check every file, write through same-directory temp files and renames, restore on
      failure, `refactor.write-failed`. Verify with "Failed write rolls back" (injected failure).

## 5. Retarget (both twins)

- [ ] 5.1 Python: same-scope check, the rename of ALIAS to TARGET's name minus ALIAS's declaration edits, no
      new-name collision check, override and shadowing refusals, duplicate-import removal, map retarget entries
      writing the target's final name. Verify with the "Retarget rewrites references to an alias" scenarios.
- [ ] 5.2 TypeScript: the same (merged declarations, duplicate import specifiers). Verify with "TypeScript merged
      alias" and Vitest.

## 6. Baseline alignment (both twins)

- [ ] 6.1 Position maps from every subcommand: edits, moved files, moved declarations (decision 33). Verify with
      unit tests over boundary, inside-span and multiline ranges.
- [ ] 6.2 Python aligner through `living_architecture.typecheck`'s runner (decisions 24, 25): two runs with temporary
      baselines, pairing, rewrite and sorted insert, `refactor.baseline-failed`, `refactor.baseline-ambiguous`.
      Verify with the Python baseline scenarios using the real basedpyright, incl. `-p` and positional-path
      commands.
- [ ] 6.3 TypeScript aligner (decisions 26, 27): pre-emit diagnostics before and after in memory, keys via
      `lang/tsc.ts`'s formatter and parser (exported), count moves. Verify with "TypeScript message names the
      symbol" (parity against real tsc) and "Ambiguous split".
- [ ] 6.4 Every subcommand prints and writes the baseline with the sources, in dry-run and apply. Verify with "Dry-run
      shows the baseline", "Moved module", "Moved declaration", "No baseline".

## 7. Literal members

- [ ] 7.1 Python probe (decision 30) in la's language server: sentinel `didChange`, diagnostics and hover diff,
      candidates, verification pass, `refactor.literal-unresolved` joining the blind-spot refusal; new-value rule.
      Verify with the Python `Literal` scenarios.
- [ ] 7.2 TypeScript: `['value']` locator to the string, the language service's rename, the new-value rule. Verify
      with "TypeScript contexts" (decision 34's contexts plus aliases and imported types).
- [ ] 7.3 Both: with `--docs`, other equal strings listed through DEV-2292's scan. Verify with "Unrelated equal
      strings untouched".

## 8. Compound names and repeatable --attr (both twins)

- [ ] 8.1 Word split and match (decision 20), `refactor.compound` lines sorted with the leftovers, only with
      `--docs`. Verify with the "--docs lists compound names" scenarios.
- [ ] 8.2 `--attr` repeatable, one scan, sorted by path, line, column, name. Verify with "Two names" through both
      twins.

## 9. dr-mock-lint --base (both twins)

- [ ] 9.1 Parsed command (help works); `--base` through `changes` (a file-at-ref helper and rename mapping added
      there in both twins); structured findings compared by path, template and non-line parameters (decision 36).
      Python lints the base text; TypeScript builds the base program through a host serving tracked files at the
      base. Verify with the "dr-mock-lint compares with a base branch" scenarios and "Base comparison in both
      blocks".

## 10. Conformance corpus

- [ ] 10.1 Cases per decision 37: paired or neutral cases for help, `--attr`, map errors, locator failures,
      `exclusive`, `--base`; adapter cases for language-only semantics (`Literal`, baseline formats, retarget forms).
- [ ] 10.2 List every new and migrated case in `conformance/INVENTORY.md`.
- [ ] 10.3 Verify every new findings template is produced by a golden and every case passes through both invoking
      twins (`scripts/conformance-cross`).

## 11. Architecture, skills and docs

- [ ] 11.1 `architecture/model.c4`: add `refactor -> typecheck` and `refactor -> changes` in `python { }`, and
      `refactor -> changes` in `typescript { }` (decision 8); run `la-arch-diagrams`. Verify `la-arch-check` passes.
- [ ] 11.2 Apply design.md "Approved wording" verbatim, after DEV-2292's wording is in place. Verify
      `npx -y @anthropic-ai/claude-code plugin validate plugin`.
- [ ] 11.3 `docs/deterministic-refactoring.md` and `docs/commands.md`: name `rename-map`, `retarget`, `--symbol`, the
      baseline alignment and `dr-mock-lint --base`; drop `--name`. Verify the docs' link checks pass.

## 12. Verification

- [ ] 12.1 Local test scope green in both twins; `ruff`, `basedpyright`, `npm run lint && npm run typecheck`,
      `la-arch-check` and `la-typecheck` pass; `scripts/sync-shared --check` passes.
- [ ] 12.2 From this checkout, dry-run on SLayer's DEV-1607 branch: a map of related method renames, a retarget map
      of DEV-2294-style twins, a rename shifting baselined columns, and a `Literal["edit_model"]` member rename;
      record wall times here (checker runs, probe, blind-spot scan).
- [ ] 12.3 Before archiving: `main` holds DEV-2292's and DEV-2289's changes archived; merge `main`;
      `openspec validate dev-2295-living-architecture-dr-refactor-names-symbols --strict`.

## 13. Post-merge (after the PR merges; not part of its diff)

- [ ] 13.1 Release a minor version (bump `python/pyproject.toml`, `node/package.json`,
      `plugin/.claude-plugin/plugin.json` together; `scripts/release-check`), release notes naming the removal of
      `--name`.
- [ ] 13.2 Pin it in SLayer; DEV-2295 stays open until the pin lands.
