## 0. Stage order and stacking (read first)

- [ ] 0.1 pr-tests writes section 1 only; pr-implement does sections 2–6. While section 1 is open the stage is
      `pr-tests`.
- [ ] 0.2 Stacked on DEV-2301. At the start of each stage, check the DEV-2301 branch: when it has commits this branch
      lacks, merge it (`git merge egor/dev-2301-living-architecture-dr-refactor-resolves-every -m "Merge branch
      'egor/dev-2301-living-architecture-dr-refactor-resolves-every' into …"`); once DEV-2301 has merged to main, merge
      `origin/main` the same way. Never rebase or stash. After DEV-2301 is archived on main, re-run
      `openspec validate dev-2310-living-architecture-python-dr-refactor-renames --strict` (this delta modifies
      requirements DEV-2301 adds or changes). DEV-2301 is still WIP: after each merge of its branch, re-check this
      delta's modified requirements against its delta and main (scenarios and prose), and decisions 8 and 13 against
      its decision 22. Verify: `git merge-base --is-ancestor` of the DEV-2301 branch head
      succeeds before opening the PR.
- [ ] 0.3 Every new conformance case is a Python `adapter` case with a hand-written golden (`golden: manual`), except
      the `--offset` case, which is `paired` (both twins); all listed in `conformance/INVENTORY.md`. Existing Python
      rename / rename-map / retarget goldens are never regenerated (design decision 16).

## 1. Tests (pr-tests)

- [x] 1.1 Conformance cases for "Name nothing resolves", "Unresolved name kept" and "A resolved local is not listed"
      (spec), producing `refactor.unresolved-name`; `shared/findings.yaml` gets the template with the approved wording
      (design decision 2) and `scripts/sync-shared` runs. Verify: the first two fail on today's code (no line), the
      third passes.
- [x] 1.2 Conformance case "Import the checker cannot resolve" stays as is (`refactor-index-unresolved-import`).
      Verify: passes on today's code.
- [x] 1.3 Module-rename cases: "Alias spelled like the module" (already pinned by `refactor-rename-module-references`;
      add a CRLF variant), "Package rename", "Module rename keeps line endings", and the import-syntax matrix of design
      decision 16 (parenthesised, multi-line, backslash, semicolon, relative, namespace package). Verify: each passes on
      today's code except "Module rename keeps line endings" (rope rewrites to the dominant newline); any other
      failure on today's code is raised with the user before writing its golden.
- [x] 1.4 Conflict-check cases (design decision 10): a member renamed onto a name a library base declares, directly
      and through a transitive library base, the library installed only in the project's environment (a venv fixture
      as DEV-2301's cache tests build); a member renamed onto a name a project ancestor declares through a base rope
      cannot evaluate. Verify: each refuses with `refactor.name-conflict`; record which pass on today's code.
      Recorded: none passes on today's code (all three rename without a conflict).
- [x] 1.5 Retarget matrix (design decision 16): direct and chained aliases, a package `__init__` barrel, star exports
      with and without `__all__`, a relative re-export, an import cycle, `MOD.ALIAS` through a re-exported module.
      Verify: pass on today's code (they pin byte-identity); a failure is raised with the user before its golden.
- [x] 1.6 "Keyword as the new name" and "Location that is not an identifier" (spec). Verify: pass on today's code.
- [x] 1.7 "A rename walks no module" (spec): a test in `python/tests/test_refactor.py` with gaps made by
      `restore_rope_visitor`, as DEV-2301's walker-gap tests do; "Walker gaps listed before any search" and "Apply writes
      nothing on a gap" become `move-symbol` tests. Verify: the rename test fails on today's code.
- [x] 1.8 Paired conformance case "Offset after CRLF line breaks" (spec "Locators"), run by both twins. Verify: the
      Python twin fails on today's code, the npm twin passes.
- [x] 1.9 Unit tests for the ports (design decision 5): `get_source_folders`, `modname` and `find_module` against
      rope's own functions over generated layouts (nested and namespace packages, a package beside a same-named module,
      `.pyi`, a symlinked directory, duplicate dotted modules in two source folders, ignored directories). Verify: fail
      before the ports exist (import error), pass against rope's own output once they do.
- [x] 1.10 Unit tests for the read/write pipeline and the diff rendering (design decisions 6 and 7): round trips for
      UTF-8 BOM, UTF-8 and Latin-1 cookies, an unknown cookie, CRLF, lone CR, mixed endings, no final newline; the
      rendered block equal to rope's `ChangeSet` description for no final newline, an empty file, CRLF and lone CR,
      non-ASCII paths, an edit plus a move; and the "Undecodable file" scenario as a conformance case (symbol and
      module rename). Verify: fail before la's renderer exists.
- [x] 1.11 Unit tests for entry location (design decisions 8 and 9): a table of locators (every binding form listed in
      decision 8, a reference resolved statically, a reference only the checker resolves, an import binding by
      `--symbol`, overloads, property accessors, a library name) with the expected kind and key, and duplicate-entry
      merging for overloads, property getter/setter, conditional and repeated assignments, an import binding beside its
      declaration. Verify: fail before the new locator exists.
- [x] 1.12 Instrumentation test: a `rename-map` of symbols and a module rename run with rope's `Rename`, `Project` and
      `ChangeSet` patched to raise; both succeed. Verify: fails on today's code.
- [x] 1.13 Existing tests that pin the old mechanism (rope `Rename`/`Project` objects built in `test_rename_union.py`,
      `test_retarget.py`, `test_rename_guards.py`, `test_rename_bindings.py`, `test_refactor.py`,
      `test_refactor_progress.py`, `test_occurrence_index.py`, `test_baseline_align.py`, `test_writer.py`, `conftest.py`
      and others that construct rename objects from rope): list each one that contradicts the plan and ask the user's
      approval to align it, naming the file and the change. Verify: approval recorded here before editing.
      Approved (user): in `test_refactor.py`, `_gap_refused` runs `move-symbol --file pkg/a.py --symbol foo --dest
      pkg/c.py` instead of a rename from `pkg/gap.py`, assertions unchanged (the crash, silent, exception-inside and
      value-error gap tests), and `test_exception_outside_ropes_walker_propagates` runs that move-symbol;
      `test_a_gap_in_a_module_rope_does_not_walk_is_not_refused` stays. No other existing test contradicts the plan.
- [x] 1.14 Entry-location rows for an `as` import alias and a re-export binding (by `--symbol` and by offset): the
      binding itself, keyed by its own site (design decisions 8 and 13); and a static-fallback case: an alias entry
      whose unresolved occurrence's static chain does not hold the binding is not renamed. Verify: fail before the new
      locator exists.

## 2. Series 1 — la's project model (pr-implement)

- [ ] 2.1 The verbatim ports (source folders, `modname`, `find_module`, `read_str_coding`) in one module; `SourceFolders`
      and every caller listed in design decision 5 read it. Verify: 1.9 passes.
- [ ] 2.2 `Session`/`Snapshot` on the project root; la's diff rendering; `emit` on la's changes, the move commands
      converting their rope `ChangeSet` at their boundary; offsets on the raw text (locators, `_raw_offset`,
      `_rope_offset`, `locators._text` removed). Verify: 1.8 and 1.10 pass.
- [ ] 2.3 Differential run (design decision 16) for series 1. Verify: no difference, or each one resolved by the user;
      then the old path is deleted and has no remaining caller.

## 3. Series 2 — entries located without rope (pr-implement)

- [ ] 3.1 The declaration-at-site algorithm, kind and key (design decisions 8 and 9), the keyword check, retarget's
      target location; `_renamer`, `_key`, `_definition_line`, `_located`'s rope branch, `_located_field`,
      `_function_at` and `_parameter_declarations` on the AST. Verify: 1.6 and 1.11 pass.
- [ ] 3.2 Differential run for series 2, then delete the old path. Verify: as 2.3.

## 4. Series 3 — unresolved names and the remaining lookups (pr-implement)

- [ ] 4.1 The static resolver in place of `RopeSites` (design decision 1) with the `refactor.unresolved-name` outcome.
      Verify: 1.1 and 1.2 pass.
- [ ] 4.2 The new export fact (design decision 10) in `lang/pyright_export.cjs` and `lang/language_server.py`, its
      self-test, its batched positions; `MemberCheck` on `hierarchy.ClassGraph`. Verify: 1.4 passes and
      `python/tests/test_pyright_export.py` covers the fact.
- [ ] 4.3 Retarget's lookups on the static resolver (design decision 11). Verify: 1.5 passes.
- [ ] 4.4 Differential run for series 3, then delete the old path (`RopeSites`, `member_namespace.Hierarchy`'s rope
      code, retarget's rope helpers). Verify: as 2.3.

## 5. Series 4 — module renames without rope (pr-implement)

- [ ] 5.1 Module-rename sites, self-alias rule, move, `--keep` (design decisions 3 and 12) replacing `_module_rename`'s
      rope path; the rename's walker-gap check removed (decision 14). Verify: 1.3 and 1.7 pass.
- [ ] 5.2 Differential run for series 4, then delete the old path. Verify: as 2.3, and 1.12 passes.

## 6. Docs, verification and gates (pr-implement)

- [ ] 6.1 Docs per design decision 18 only after the user approves its exact wording; record the approval here. Verify:
      `rg -n -i "rope" plugin docs` reviewed, every remaining mention true of moves or the walker contract.
- [ ] 6.2 SLayer DEV-1607 map, dry run on a `git archive` copy (`.venv` symlinked, never written), old and new path
      compared per design decision 16. Verify: identical output recorded in a Linear comment on DEV-2310.
- [ ] 6.3 Local test scope per `/la:pr`, `uv run ruff check src tests`, `uv run basedpyright src tests`,
      `scripts/sync-shared --check`, `la-arch-check`, `npx -y @anthropic-ai/claude-code plugin validate plugin`, and
      `npm run build && npm run conformance` for the paired case. Verify: all green.
