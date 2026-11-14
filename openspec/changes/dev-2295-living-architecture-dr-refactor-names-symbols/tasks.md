## 0. Stage order (read first)

- [x] 0.1 pr-tests: write the failing tests for every scenario of this change's delta specs (unit tests in both
      twins; conformance cases per design decision 37, listed in `conformance/INVENTORY.md`), then a Codex review of
      the tests against the plan. This branch already holds DEV-2292's failing tests, so `/la:pr` stage detection
      picks `pr-implement`: run this stage by naming `pr-tests` when invoking `/la:pr`. DEV-2292's tests stay
      failing alongside; do not touch them.
- [x] 0.2 Precondition for pr-implement: DEV-2292's implementation is merged into this branch (merge its branch, or
      `origin/main` once it has landed), and DEV-2292's tests pass here. Do not start section 1 before that.

- [x] 0.3 Merge `origin/main` (decision 38), before any other open task. In order: (a) commit the working tree
      (the `--name` → `--symbol` case migrations and the symbol-path work in progress), naming each file;
      (b) `git merge origin/main` with a message whose first line holds `'origin/main'` in single quotes;
      (c) keep what git merges cleanly; resolve conflicts with `main`'s side for every conflicted file (the eight `refactor-rename-*` case directories,
      `python/tests/test_rename_docs.py`, `python/tests/test_rename_strings.py`, the archived DEV-2292 change),
      then redo this change's edits on them (`--symbol` in their `case.yaml`; in `node/src/refactor/workspace.ts`
      keep both `main`'s service-valued map and this change's overlay argument, adapting this change's callers; the
      `dr-mock-lint` hunk in `mocks.ts` likewise); `conformance/INVENTORY.md` as the union of both sides' rows;
      `scripts/sync-shared` for both `CONTRACT_HASH` files; (d) this branch's unarchived
      `openspec/changes/dev-2292-…` folder is gone after the merge (only the archive remains). Verify:
      `scripts/sync-shared --check`, `openspec validate dev-2295-living-architecture-dr-refactor-names-symbols
      --strict`, `la-arch-check`, and DEV-2292's tests and cases pass as on `main` apart from the ones this change's
      open tasks own.
- [ ] 0.4 Align this change's tests with decisions 39–46 (they were written before them): the `Literal` tests and
      cases that pin "listed only with `--docs`" now expect the listing without it and the `Other` argument unlisted
      (decision 40); add the shared vectors of decision 41 (`shared/vectors/`, `scripts/sync-shared`, a runner in
      each twin, failing until tasks 3, 6.1 and 8.1); a `--symbol` test on a TypeScript member declared by a
      computed name (decision 44); a two-name `--attr` test over a string-member form and a TypeScript element
      access (decision 46); a map `--with` (exit 2, `refactor.computed-stand-in`) and `--without` on a computed-name
      stand-in (decision 44); a map whose second entry renames the class a patch target of the first resolves to
      (rewritten, not "unrelated"; decision 39); `Literal`, compound-name and retarget runs with a source in an
      excluded directory and, for TypeScript, one outside every program (decision 42); the "Position that accepts
      any string is listed" scenario in both twins. Verify each new test fails for the missing behaviour, not for
      an error.

## 1. Shared contract

- [x] 1.1 `shared/cli.yaml`: `--symbol` on `rename` and `move-symbol`, `--name` removed; an `exclusive` group
      `[offset, line, symbol]` on both, and the manifest header comment documents `exclusive`; subcommand `rename-map`
      (positional `map`, `rename`'s options minus the locator and `--new-name`); subcommand `retarget` (`--file`,
      the locators, `--target`, `--allow-blindspots`, `--with`, `--without`, `--keep`, `--docs`); `--attr`
      `repeatable: true` on `dr-compliance`; `dr-mock-lint` not `passthrough`, with positional `paths` (`+`) and
      `--base`. Verify with both twins' CLI vector and manifest tests.
- [x] 1.2 `shared/findings.yaml`: `refactor.symbol-unresolved`, `refactor.symbol-ambiguous`, `refactor.map-invalid`,
      `refactor.map-mixed-languages`, `refactor.map-duplicate`, `refactor.map-conflict`, `refactor.retarget-header`,
      `refactor.retarget-scope`, `refactor.retarget-override`, `refactor.retarget-shadowed`,
      `refactor.write-failed`, `refactor.baseline-ambiguous`, `refactor.baseline-failed`, `refactor.literal-value`,
      `refactor.literal-unresolved`, `refactor.compound`; drop templates only `--name` used. Verify every new
      template is produced by a golden (task 10.3).
- [x] 1.3 `shared/schema/rename-map.schema.json` (decision 13). Verify with schema unit tests in both twins (valid
      entries, both intents, two locators, unknown key).
- [x] 1.4 `scripts/sync-shared`; verify `scripts/sync-shared --check` and the drift tests pass.

## 2. CLI manifest `exclusive` (both twins)

- [x] 2.1 Both parser builders reject more than one option of an `exclusive` group with exit 2. Verify with the
      "Exclusive options rejected together" scenario through both twins.

## 3. Symbol paths (both twins)

- [x] 3.1 Python: parse Q, walk the module AST (module, class, `self.NAME`, `<locals>`, `(param)`, `['value']`),
      group declarations by checker symbol (decision 32), candidates on failure, exit 2. Verify with the "Symbols are
      located by their path in a file" scenarios and one test per grouping construct.
- [x] 3.2 TypeScript: the same over the TypeScript AST and checker symbols (members, enums, namespaces, type
      literals through aliases, locals, parameters, `['value']`). Verify with Vitest and "TypeScript member and
      local by path".
- [x] 3.3 Remove `--name` from both twins; migrate every conformance case using it to `--symbol` (the goldens are
      unchanged except where a case pinned `--name`'s guess, e.g. `refactor-ts-rename-name-prefers-declaration`,
      `refactor-ts-symbol-not-found`, which change to the new findings), including every case and test `main`
      brought in (decision 45); no `--name` remains under `conformance/`, `python/tests`, `node/test`, `docs` or
      `plugin`. Verify with `scripts/conformance-cross`.
- [x] 3.4 Path parsing passes the shared symbol-path vectors in both twins; candidate lines come from the twin's
      line index (decision 41); a computed-name member is not a candidate (decision 44).

## 4. Map engine (both twins)

- [x] 4.1 Python: load and validate MAP; one language; resolve every locator first; canonicalise symbols
      (decision 31); one snapshot, one language server, each rename rule once over the union; one blind-spot scan
      for every member entry's old name; every rule's outcomes filed by DEV-2292's driver, "unchanged declaration"
      judged against the whole symbol set (decision 39); sources read through the file universe (decision 42);
      merge edits, `refactor.map-conflict`; `rename` routed through it. Verify
      with the "Rename maps apply many renames as one" scenarios and "Single rename equals its map".
- [x] 4.2 TypeScript: the same over one workspace session. Verify with Vitest.
- [x] 4.3 Routing: `rename-map` routes by its entries' files, forwarding raw argv to the other twin. Verify with
      "TypeScript map through the PyPI twin".
- [x] 4.4 Writer (both twins): re-check every file, write through same-directory temp files and renames, restore on
      failure, `refactor.write-failed`. Verify with "Failed write rolls back" (injected failure).

## 5. Retarget (both twins)

- [x] 5.1 Python: same-scope check, the rename of ALIAS to TARGET's name minus ALIAS's declaration edits, no
      new-name collision check, override and shadowing refusals, duplicate-import removal, map retarget entries
      writing the target's final name; outcomes per site as any rename rule (decision 39). Verify with the
      "Retarget rewrites references to an alias" scenarios.
- [x] 5.2 TypeScript: the same (merged declarations, duplicate import specifiers). Verify with "TypeScript merged
      alias" and Vitest.

## 6. Baseline alignment (both twins)

- [x] 6.1 Position maps from every subcommand: edits, moved files, moved declarations (decision 33). Verify with
      unit tests over boundary, inside-span and multiline ranges, and the shared range-transform vectors in both
      twins (decision 41).
- [x] 6.2 Python aligner through `living_architecture.typecheck`'s runner (decisions 24, 25): two runs with temporary
      baselines, pairing, rewrite and sorted insert, `refactor.baseline-failed`, `refactor.baseline-ambiguous`.
      Verify with the Python baseline scenarios using the real basedpyright, incl. `-p` and positional-path
      commands.
- [x] 6.3 TypeScript aligner (decisions 26, 27): pre-emit diagnostics before and after in memory, keys via
      `lang/tsc.ts`'s formatter and parser (exported), count moves. Verify with "TypeScript message names the
      symbol" (parity against real tsc) and "Ambiguous split".
- [x] 6.4 Every subcommand prints and writes the baseline with the sources, in dry-run and apply. Verify with "Dry-run
      shows the baseline", "Moved module", "Moved declaration", "No baseline".

## 7. Literal members

- [x] 7.1 Python probe (decision 30) in la's language server: sentinel `didChange`, diagnostics and hover diff,
      candidates, verification pass, `refactor.literal-unresolved` joining the blind-spot refusal; new-value rule;
      built as rounds of DEV-2292's probe object over the file universe (decisions 42, 43). Verify with the Python
      `Literal` scenarios.
- [x] 7.2 TypeScript: `['value']` locator to the string, the language service's rename, the new-value rule. Verify
      with "TypeScript contexts" (decision 34's contexts plus aliases and imported types).
- [x] 7.3 Both: every other string equal to OLD gets an outcome through DEV-2292's exact-OLD literal rule, with or
      without `--docs`: unrelated when the checker types it by another literal type (TypeScript: contextual type;
      Python: the last probe round), else `leftover` (decision 40). Verify with "Unrelated equal strings
      untouched".

## 8. Compound names and repeatable --attr (both twins)

- [x] 8.1 Word split and match (decision 20), `refactor.compound` lines sorted with the leftovers, only with
      `--docs`; declarations from the file universe, outcomes through the driver (decisions 39, 42). Verify with
      the "--docs lists compound names" scenarios and the shared word-split vectors in both twins (decision 41).
- [x] 8.2 `--attr` repeatable, one scan, sorted by path, line, column, name. Verify with "Two names" through both
      twins.
- [x] 8.3 After the merge, the repeatable `--attr` covers `main`'s access forms (decision 46). Verify with task
      0.4's two-name test.

## 9. dr-mock-lint --base (both twins)

- [x] 9.1 Parsed command (help works); `--base` through `changes` (a file-at-ref helper and rename mapping added
      there in both twins); structured findings compared by path, template and non-line parameters (decision 36).
      Python lints the base text; TypeScript builds the base program through a host serving tracked files at the
      base. Verify with the "dr-mock-lint compares with a base branch" scenarios and "Base comparison in both
      blocks".

## 10. Conformance corpus

- [x] 10.1 Cases per decision 37: paired or neutral cases for help, `--attr`, map errors, locator failures,
      `exclusive`, `--base`; adapter cases for language-only semantics (`Literal`, baseline formats, retarget forms).
- [x] 10.2 List every new and migrated case in `conformance/INVENTORY.md`.
- [x] 10.3 Verify every new findings template is produced by a golden and every case passes through both invoking
      twins (`scripts/conformance-cross`).

## 11. Architecture, skills and docs

- [x] 11.1 `architecture/model.c4`: add `refactor -> typecheck` and `refactor -> changes` in `python { }`, and
      `refactor -> changes` in `typescript { }` (decision 8); run `la-arch-diagrams`. Verify `la-arch-check` passes.
- [x] 11.2 Apply design.md "Approved wording" verbatim, after DEV-2292's wording is in place. Verify
      `npx -y @anthropic-ai/claude-code plugin validate plugin`.
- [x] 11.3 `docs/deterministic-refactoring.md` and `docs/commands.md`: name `rename-map`, `retarget`, `--symbol`, the
      baseline alignment and `dr-mock-lint --base`; drop `--name`. Verify the docs' link checks pass.

## 12. Verification

- [x] 12.1 Local test scope green in both twins; `ruff`, `basedpyright`, `npm run lint && npm run typecheck`,
      `la-arch-check` and `la-typecheck` pass; `scripts/sync-shared --check` passes.
- [ ] 12.2 From this checkout, dry-run on SLayer's DEV-1607 branch: a map of related method renames, a retarget map
      of DEV-2294-style twins, a rename shifting baselined columns, and a `Literal["edit_model"]` member rename;
      record wall times here (checker runs, probe, blind-spot scan).
- [ ] 12.3 Before archiving: `main` holds DEV-2292's and DEV-2289's changes archived (true as of task 0.3's merge);
      merge `main` again;
      `openspec validate dev-2295-living-architecture-dr-refactor-names-symbols --strict`.

## 13. Post-merge (after the PR merges; not part of its diff)

- [ ] 13.1 Release a minor version (bump `python/pyproject.toml`, `node/package.json`,
      `plugin/.claude-plugin/plugin.json` together; `scripts/release-check`), release notes naming the removal of
      `--name`.
- [ ] 13.2 Pin it in SLayer; DEV-2295 stays open until the pin lands.
