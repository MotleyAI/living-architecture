## 0. Stage order and repro (read first)

- [x] 0.1 pr-tests writes section 1 only; pr-implement does sections 2–4. While section 1 is open, the stage is
      `pr-tests`. Verify: every task of section 1 is ticked before any task of section 2 starts.
- [ ] 0.2 Repro of the DEV-1607 map (158 entries):
      1. In SLayer's main checkout (`~/GitHub/SLayer/slayer`), run `git archive 452a2f57` into a temp directory.
      2. There, `git init` and commit everything (without a git repository la finds no project files).
      3. Symlink `.venv` to `~/GitHub/SLayer/slayer.worktrees/egor__dev-1607-rename-columns-to-fields-to-be-consistent-with/.venv`.
      4. Set `LA_CACHE_DIR` to a fresh temp directory for a cold run.
      5. From the snapshot, run `/usr/bin/time -v <la>/python/.venv/bin/dr-refactor --timings rename-map openspec/changes/dev-1607-rename-columns-to-fields-to-be-consistent-with/rename-map.yaml --docs <flags> --without tests/test_ossie_vocabulary_custom_backend.py:152`,
         `<flags>` being every `--keep`/`--with`/`--without` line of the map's header:
         `sed -n 's/^#   \(--\(keep\|with\|without\) .*\)$/\1/p' <map>`. `--timings` goes before the subcommand.

      Never write to SLayer. Verify: the run exits 0 and prints `timing: conflicts`.
- [ ] 0.3 Repro of the DEV-2318 map (2,272 entries):
      1. In `~/GitHub/SLayer/slayer.worktrees/egor__dev-2318-ossie-vocabulary-names-only-dataset-field`, run
         `git archive a944edb08` (the commit before the map was applied) into a temp directory.
      2. Write the map as applied into it: `git show 1fe8a2940:openspec/changes/dev-2318-ossie-vocabulary-names-only-dataset-field/rename-map.yaml`.
      3. `git init` and commit everything; symlink `.venv` to that worktree's `.venv`; set `LA_CACHE_DIR` fresh.
      4. Run as in 0.2 with that map, `--docs` and `<flags>` taken from the header of the worktree's copy of the map
         (the map at `1fe8a2940` has none; its entries are identical):
         `sed -n 's/^#   \(--[a-z-]*\)\( .*\)\?$/\1\2/p' <worktree map>` (167 lines, `--allow-blindspots` among them).

      Never write to SLayer. Verify: the run exits 0 and prints `timing: conflicts`.
- [ ] 0.4 Run every measurement alone on the machine, and record its load, free memory and swap with the numbers: a
      contended run once tripled a phase's time.

## 1. Tests (pr-tests)

- [x] 1.1 Liveness at the start of `conflicts`, `test_rename_map.py` (or a new `test_rename_map_lifetime.py`): on a
      map with a member rename, a retarget and a `--docs` mention, weak-reference while `rules` runs every rename
      worker, the `RunIndex`, the `TypeFacts`, the `EntryLocator`, `session.tables`, a parsed `SourceFile` of the
      snapshot and a file read from outside the project; at the start of `check_names`, after `gc.collect()`, every
      reference is dead. Verify: fails today.
- [x] 1.2 A finished group's workers are dead before the next group's rules run: a map with two old-name groups, weak
      references to group 1's workers checked when group 2's first worker's `rules` starts. Verify: fails today.
- [x] 1.3 Every path ends `rules` the same way: a `--fail-fast` stop in `references`, a `--fail-fast` stop in
      `rules`, a failed entry, and an entry whose new name equals its old one. Each run's stdout and stderr equal
      today's (the existing tests' expectations, or recorded before the change), and no worker is alive at the start
      of the report. Verify: the output assertions pass today; the liveness ones fail.
- [x] 1.4 Leftovers held once: a `--docs` map whose entries share an old name, mentioned in prose and code. Every
      leftover key is held once (count the leftover `Finding`s alive at the start of `conflicts`, or the store's
      size), and the printed findings equal today's. Verify: the count fails today; the output passes.
- [x] 1.5 Leftover `end` semantics: two copies of one key `(path, line, col, text)` with different `end`s, and a final
      edit covering only one span: the key is printed; with both spans covered, it is not. Test through the store
      and `findings()`. Verify: fails today on the new store.
- [x] 1.6 Retarget imports and keeps: several retargets needing imports in the same home, one of them held by
      `--keep`. Assert the byte-identical diff, which entry each import belongs to (via a conflict naming it), and
      `refactor.keep-unmatched` present or absent as today. Verify: passes today, and pins it.
- [x] 1.7 Class facts after `rules`, with the real checker:
      - a member renamed to a name another class declares in an NFKC-equivalent spelling, in a file that does not
        spell the new name (a miss): output equals today's;
      - a member renamed to an NFKC-equivalent spelling of a name another class declares (a miss): output equals
        today's;
      - on a miss, the run's `ServerSession` starts a fresh language server (count starts), and a server failure then
        gives today's `refactor.pyright-failed` refusal;
      - a fact `prepare` merged is answered without any export.

      Verify: the output assertions pass today; the source's own assertions fail today on the new source.
- [x] 1.8 A single-entry module `rename` (and a module `rename` in a one-entry map) still computes today's output: the
      end of `rules` never runs on the module-rename branch. Verify: passes today, and pins it.
- [x] 1.9 No `ImportNeed` outlives the import plan: on a map whose retargets need imports, weak-reference their needs'
      AST nodes and check them dead at the start of `conflicts`. Verify: fails today.
- [x] 1.10 Align `test_refactor_progress.py`'s `keyed` case to patch the keyed check on its new owner, the result
      type (`SymbolRename.check_conflicts` moves there). The assertion, charged to `conflicts` only, is unchanged.
      Verify: fails today only on the missing owner.
- [x] 1.11 Codex review of the tests against this plan (`reviewers.codex`). Verify: findings resolved with the user.

## 2. Implementation (pr-implement)

- [x] 2.1 The result type (a `BaseModel` in `refactor`) and the workers' conversion to it, per decision 1:
      `SymbolRename`, `AliasRetarget` and `LiteralRename` each yield one. `check_conflicts` and `renamed_members`
      move onto the result, reading the snapshot passed in. A result holds no AST node, `SourceFile` or `ImportNeed`.
      Verify: `basedpyright` clean; 1.10 passes.
- [x] 2.2 `rename_map.py`: `rules` converts each group's workers when the group finishes and drops them; retargets'
      `ImportNeed`s go to a side list that the one import plan after the last group consumes and drops (decision 2);
      leftovers go to the run-wide store after the keeps filter them with `mark=False` (decision 5). Verify: 1.2,
      1.4, 1.5, 1.6 and 1.9 pass.
- [x] 2.3 The step ending `rules` on every path but the module-rename branch (decision 3): converts each worker left
      as it stands, closes the `RunIndex` (saving the cache) and the run's `ServerSession`, keeps only the class-fact
      source, which exports a miss through that `ServerSession` (decision 4), and releases `TypeFacts`, the
      `EntryLocator`, `session.tables`, the outside files and the snapshot's parsed forms. `run`'s and `run_map`'s
      `finally` still close the index and the server on any failure. Verify: 1.1, 1.3, 1.7 and 1.8 pass.
- [x] 2.4 Site resolution, the report, the name checks, `findings()` and the outputs take only results. Verify:
      `test_rename_map.py`, `test_refactor_progress.py` and the rename and retarget tests pass.
- [x] 2.5 Local test scope (per `/la:pr`) plus the conformance corpus through the Python twin, then
      `uv run ruff check src tests` and `uv run basedpyright src tests` in `python/`, `la-typecheck` and
      `la-arch-check`. Verify: all green.

## 3. Measurement (pr-implement)

- [ ] 3.1 Cold runs of both maps (0.2, 0.3) under `/usr/bin/time -v`, alone, on main at the merge (before) and on this
      change: peak RSS, phase split, total. Verify: DEV-1607 peak at most 3.0 GB (main 3.74 GB, prototype 2.84 GB);
      DEV-2318 peak at most 4.0 GB (main 9.84 GB, prototype 3.91 GB); total no slower than before. Results go in a
      comment on DEV-2323 with the machine's state (0.4).
- [ ] 3.2 Differential: for each map, both runs' stdout and refusal reports (stderr without the `[...]` progress and
      `timing:` lines) are byte-identical. Verify: `diff` output recorded in the same comment.

## 4. Docs

- [x] 4.1 No user-facing doc names the workers' fields, the leftover store or the index's internals. Check with
      `grep -rn "leftovers\|RunIndex\|SymbolRename" docs plugin README.md` and record the result. Verify: no hit, or
      each hit updated.
