## 1. Shared contract

- [x] 1.1 In `shared/findings.yaml`, change `refactor.keep-unmatched` and `refactor.not-stand-in` and add
  `refactor.keep-unmatched-near` and `refactor.keep-unneeded`, verbatim as in design.md decision 4 (user, approved
  wording); run `scripts/sync-shared` and verify `scripts/sync-shared --check` passes.

## 2. Tests first (pr-tests)

- [x] 2.1 Conformance, new paired (python + typescript) cases on a small fixture, each listed in
  `conformance/INVENTORY.md` with `golden: manual` goldens. Verify each fails before the implementation:
  - unneeded whole-file keep, `--apply`: exit 0, rename written, `refactor.keep-unneeded` after the last `[rules]`
    line and before `[conflicts]`;
  - unneeded directory keep, `--apply`: the same;
  - late unmatched line keep with edits in its file, `--apply`: `refactor.keep-unmatched-near` naming the nearest
    edited line (include a tie, so the earlier line is named), `[rules]` lines, no `[conflicts]`, exit 2, nothing
    written;
  - late unmatched line keep in a file without edits: late `refactor.keep-unmatched`, no `[conflicts]`, exit 2;
  - comment-only line keep without `--docs`: refused in `checks`, no `[references]`, exit 2. Variants: a trailing
    comment on a code line whose code doesn't spell the old name, and a line inside a multi-line comment (TS: a
    JSDoc `@param` line of a parameter rename);
  - the same comment keep with `--docs --apply`: full phase sequence, every other mention rewritten, the kept line
    unchanged, exit 0;
  - unneeded whole-file keep plus an unmatched line keep: the warning, then the final report, no `[conflicts]`,
    exit 2;
  - unneeded whole-file keep plus a blind spot: the warning, `[conflicts]`, the final report with the blind spot,
    exit 1;
  - late unmatched line keep plus a blind spot (the "Late unmatched keep with other refusals" scenario): no
    `[conflicts]`, the blind spot, the keep finding, the `refactor.blindspots` line, exit 2;
  - a `--with` stand-in's comment line under the comment rule (paired where the TS twin accepts the input, else
    Python adapter).
- [x] 2.2 Conformance, new Python adapter cases: a type-comment keep (`# type: Old` only) passes `checks`; a module
  rename with an unneeded file keep (warning, exit 0), with a stale line keep (refused before `[conflicts]`), with a
  directory keep covering the moved package (no warning, not moved, exit 0), and with `--with` (`not-stand-in` in
  `checks`, no `[references]`).
- [x] 2.3 Realign the existing goldens this plan changes (approved with the plan), keeping each case's intent and
  updating its `note`:
  - `refactor-progress-keep-no-old-name`: the dir keep passes `checks`, warning, exit 0;
  - `refactor-progress-keep-prose-no-docs`: the file keep warns, exit 0. Add a line-keep variant in a prose file
    (refused in `checks` without `--docs`);
  - `refactor-progress-late-keep`: the whole-file keep is now a warning before `[conflicts]`; the blind spot still
    refuses;
  - `refactor-progress-bad-keeps`: switch its two "holding no old name" keeps to line keeps so all three findings
    stay in `checks`;
  - `refactor-progress-keep-escaped`, `refactor-progress-keep-filtered`, `refactor-progress-unresolved-and-keep`,
    `refactor-rename-keep`, `refactor-ts-rename-keep`, `refactor-rename-module-keep`,
    `refactor-rename-module-keep-file`: re-check against the new rules and realign only where output changes;
  - `refactor-rename-not-stand-in`, `refactor-ts-rename-not-stand-in`: new text, no `[conflicts]`;
  - `refactor-rename-module-not-stand-in`: refused in `checks`, new text;
  - `refactor-rename-keep-unmatched`, `refactor-ts-rename-keep-unmatched` (`:99`, `site-missing`): unchanged.
- [x] 2.4 Unit tests. Python (`tests/test_rename_guards.py`, `tests/test_refactor_progress.py`, `tests/test_contract.py`
  as needed), plus helper tests: comment-aware `spelled_lines` / `keep_spells` (plain comment, trailing comment, type
  comment, `--docs` on), nearest edited line (before, after, tie, none), and whole-path keeps skipped by the
  up-front check. TS (`node/test/rename-guards.test.ts`) mirrors the helpers. Verify they fail before the
  implementation.

## 3. Python twin

- [x] 3.1 `sites.py`: comment-aware spelling (without `--docs`, exclude `tokenize` COMMENT tokens other than type
  comments), and `keep_checks` applies to line keeps only. Verify with the 2.4 helper tests.
- [x] 3.2 `rename_map.py`: a site-resolution step after `rules()` (which ends with `_imports`), skipped when stopped
  or when an entry failed. It prints `refactor.keep-unneeded` lines, builds `not-stand-in` and the line-keep
  findings with the nearest edited line, and stops before `[conflicts]` on any refusing one. `report()` then no
  longer runs `site_findings`. Verify with the 2.1 / 2.3 Python cases.
- [x] 3.3 `rope_refactor.py` (`_module_rename`): keeps resolved after `_kept`, before `[conflicts]` (warning or
  refusal with the nearest edited line); `--with` / `--without` refused in `RenameMap.checks` for a module rename.
  Verify with the 2.2 cases.

## 4. TypeScript twin

- [x] 4.1 `sites.ts` / `rename.ts` `checks`: the comment rule (via `sourceRegions`) and line keeps only. Verify with
  the 2.4 TS helper tests.
- [x] 4.2 `rename.ts` `runEntries`: `planImports` before site resolution; site resolution (warnings, `not-stand-in`,
  `computed-stand-in`, line-keep findings with the nearest edited line) before `[conflicts]`, stopping on a refusing
  finding. Verify with the paired cases through `npm run build && npm run conformance`.

## 5. Docs and gates

- [x] 5.1 `docs/deterministic-refactoring.md`: the `checks` list ("keeps whose files never spell an old name"
  becomes line keeps whose line spells no old name, comments not counting without `--docs`), plus one sentence on
  site resolution (a warning for an unneeded whole-file or directory keep; a stop before `conflicts` on an unmatched
  line keep or a stand-in site that holds none). Verify by reading it against the spec delta.
- [x] 5.2 Run the local test scope (la-affected-tests plus the changed conformance cases through
  `scripts/conformance-cross`), `ruff`, `basedpyright`, `npm run lint && npm run typecheck`, `la-arch-check`,
  `la-typecheck`, and verify that every one passes and that every new `findings.yaml` template is produced by a
  golden.
