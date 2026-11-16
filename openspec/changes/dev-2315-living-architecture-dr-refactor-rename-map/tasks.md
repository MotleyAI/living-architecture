## 0. Stage order (read first)

- [x] 0.1 pr-tests writes section 1 only; pr-implement does sections 2–6. While section 1 is open the stage is
      `pr-tests`. Verify: every task of section 1 is ticked before any of section 2 starts.
- [x] 0.2 DEV-2301 (PR #51) and DEV-2307 (PR #52) are merged into this branch but not yet into `main`. Before opening
      the PR, check whether both have merged; if so merge `origin/main` first (`git merge origin/main -m "Merge branch 'origin/main' into …"`;
      never rebase or stash) and re-run the local test scope. Verify: `git log origin/main..HEAD` holds only this
      change's commits.
- [x] 0.3 Repro for every SLayer measurement: `git archive` SLayer's branch
      `egor/dev-1607-rename-columns-to-fields-to-be-consistent-with` into a temp directory, `git init` it and commit
      (without a git repository la finds no project files), symlink the worktree's `.venv`, set `LA_CACHE_DIR` to a
      temp directory. Run from the snapshot: `dr-refactor --timings rename-map openspec/changes/dev-1607-…/rename-map.yaml
      --docs <the flags in the map's header> --without tests/test_ossie_vocabulary_custom_backend.py:152` (`--timings`
      goes before the subcommand). Never write to SLayer. Verify: the run reaches `[references]`.

## 1. Tests (pr-tests)

- [x] 1.1 `test_language_server.py`: a fake-server message of several MB delivered in small chunks is read with
      linear copying (count chunk copies, not wall time). Verify: fails on today's `_pump`.
- [x] 1.2 `test_pyright_export.py`: the fake bundles gain the `enableAmbientAnalysis` line; a new test asserts a
      bundle without it is refused as `mismatch`, and one that the patched bundle sets it false. Verify: the new
      tests fail today.
- [x] 1.3 Sharding seam: exporting a multi-file fixture's files in two requests and merging gives the same
      `RunIndex` state as one request, through the fake server and (integration-marked) the real one, including
      definitions shared across the partition. Verify: passes or fails today; a failure is fixed in 2.3.
- [x] 1.4 Follow guard (DEV-2307's) with the cache: on a fixture importing a library class, where a rule fetches a
      skipped library fact on demand, a cold and a warm run give identical facts and output. Verify: passes or fails
      today; a failure is fixed in 2.3.
- [x] 1.5 Rules: two entries sharing a file and an old name but targeting different classes give each its own
      edits (no state leaks through the shared candidates), and a counting test that a candidate file's sink
      discovery runs once for both. Verify: the counting test fails today.
- [x] 1.6 Conflict checks, unit tests on `BindingCheck`: a class-body declaration renamed onto an existing one; a
      renamed global seen through a star import in an unedited file; a two-step star chain; an edited `__all__`; a
      retarget's added import; a file with an attribute edit and a name edit; a length-changing attribute edit before
      a binding edit in one file. Verify: all pass today (they pin behaviour the narrowing must keep).
- [x] 1.7 Conflict checks, counting tests: a file whose only edits are attribute or keyword names is not re-parsed;
      the all-together pass reuses a single-entry state; a run with moved files re-judges every file. Verify: the
      first two fail today.
- [x] 1.8 `MemberCheck`: the project scan for classes declaring a member name runs once per name for several
      renamed members. Verify: fails today.
- [x] 1.9 `conflicts` phase, both twins: unit tests that a keyed-only, a member-only, a binding and a map conflict
      are each charged to `conflicts` and none to `resolve`; that `[conflicts]` precedes the finding; that a
      standalone Python module rename prints `[references]`, `[conflicts]` and times its check there; that
      `--fail-fast` after a refused group prints no `[conflicts]`. Verify: fail today.
- [x] 1.10 Conformance: a new case for each new spec scenario not already covered ("Conflict checks timed on their
      own", "Name conflict found in its phase", "Module rename conflicts", "No conflict phase after a fail-fast
      stop"), listed in `conformance/INVENTORY.md`. Verify: they fail today on the missing line.
- [x] 1.11 Leftovers across entries: a unit test in `test_rename_map.py` and an adapter conformance case (Python;
      only the Python twin lists keyed-string leftovers) for "Another entry's rewrite is no leftover", listed in
      `conformance/INVENTORY.md`. Verify: both fail today on the four `leftover` lines.

## 2. Export and server

- [x] 2.1 `_pump` collects chunks and joins once. Verify: 1.1 passes.
- [x] 2.2 The export preload's anchor turning ambient analysis off. Verify: 1.2 passes, and the `Literal` and
      `--attr` tests pass.
- [x] 2.3 Whatever 1.3 and 1.4 show failing in the export or the index cache. Verify: 1.3 and 1.4 pass.

## 3. Rules

- [x] 3.1 Neutral per-(file, old name) sink candidates for `keyed.scan` through `RunIndex.memo`; each entry
      classifies them. Verify: 1.5 passes.
- [x] 3.2 The other name-only scans computed once per (file, name): member declarations, `--docs` mentions and
      source regions, compound names, text-table declarations. Verify: a cProfile of the 11 `measures` entries
      (`grep -E "symbol: (\S+\.)?measures[,}]"` of the map, `--docs`, no site flags) shows each called once per file.
- [x] 3.3 `Session.source` (`rename_union.py`) becomes a plain lookup. Verify: in the same profile, its calls after a
      file's first read take under 1 s in all.
- [x] 3.4 The final report drops a leftover at a site any entry rewrites. Verify: 1.11 passes.

## 4. Conflict checks

- [x] 4.1 Binding-relevant edits: re-parse only files with one, analyse and map offsets from those edits, cache the
      state by them; the full check whenever files move. Verify: 1.6 and 1.7 pass.
- [x] 4.2 Judge only re-parsed files and their transitive star importers. Verify: 1.6 passes.
- [x] 4.3 `MemberCheck` finds the classes declaring a name once per name. Verify: 1.8 passes.

## 5. The `conflicts` phase

- [x] 5.1 `shared/cli.yaml`: `conflicts` after `rules` in `timing_phases`; run `scripts/sync-shared`. Verify:
      `scripts/sync-shared --check` passes.
- [x] 5.2 Python twin: the phase around map conflicts, the binding, member and keyed checks in `rename_map.py`, and
      around the binding check in `rope_refactor.py`'s module rename. Verify: the Python tests of 1.9 pass.
- [x] 5.3 npm twin: the phase around `mapConflicts` and `nameConflicts` in `rename.ts`. Verify: the npm tests of 1.9
      pass.
- [x] 5.4 Goldens: regenerate with `LA_UPDATE_GOLDENS=1`, edit `golden: manual` cases by hand, and review that every
      golden diff is exactly the added `[conflicts]` line (and the `conflicts` timing line where timings are
      pinned). The commit message states the reason. Verify: `scripts/conformance-cross` passes for both twins.
- [x] 5.5 `docs/deterministic-refactoring.md` names the phase where it lists phases. Verify: `grep -n "rules" docs/*.md`
      shows no phase list without `conflicts`.
- [x] 5.6 Refresh the three `pytest-split` duration files (`python/tests/durations/`) for the new tests, as
      `docs/development.md` describes. Verify: `test_ci_split.py` passes.

## 6. Measurement

- [ ] 6.1 Cold run of the DEV-1607 map (0.3) under `/usr/bin/time -v`, on the merge commit before this change's
      code (the "before", with DEV-2307's follow guard) and after it: phase split, total, peak memory, the export's
      follow count. Verify: recorded in a comment on DEV-2315.
- [ ] 6.2 Warm re-run with one more `--without` site: a cache hit (no export time) and stdout equal to the cold
      run's. Verify: recorded in the same comment.
- [ ] 6.3 Differential: the cold run's stdout and refusal report against the same run on the commit before this
      change, byte-identical apart from the `[conflicts]` line. Verify: `diff` output recorded in the comment.
- [ ] 6.4 CI: the PR's `test` and `cross-twin` shard times against DEV-2307's (PR #52) sharded runs.
      Verify: recorded in the comment.
