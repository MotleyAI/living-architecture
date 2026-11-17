## 0. Stage order and repro (read first)

- [x] 0.1 pr-tests writes section 1 only; pr-implement does sections 2–4. While section 1 is open, the stage is
      `pr-tests`. Verify: every task of section 1 is ticked before any task of section 2 starts.
- [x] 0.2 Repro for every SLayer measurement:
      1. In SLayer's main checkout (`~/GitHub/SLayer/slayer`), run `git archive 452a2f57` into a temp directory.
      2. There, `git init` and commit everything (without a git repository la finds no project files).
      3. Symlink `.venv` to `~/GitHub/SLayer/slayer.worktrees/egor__dev-1607-rename-columns-to-fields-to-be-consistent-with/.venv`.
      4. Set `LA_CACHE_DIR` to a fresh temp directory for a cold run.
      5. From the snapshot, run `/usr/bin/time -v <la>/python/.venv/bin/dr-refactor --timings rename-map openspec/changes/dev-1607-rename-columns-to-fields-to-be-consistent-with/rename-map.yaml --docs <flags> --without tests/test_ossie_vocabulary_custom_backend.py:152`.
         `<flags>` is every `--keep`/`--with`/`--without` line of the map's header (570 words), e.g.
         `sed -n 's/^#   \(--\(keep\|with\|without\) .*\)$/\1/p' <map>`. `--timings` goes before the subcommand.
      6. Run alone on the machine: one run contended by another job, with swap full, gave a `conflicts` phase of
         261 s instead of 101 s.

      Never write to SLayer. Verify: the run exits 0 and prints `timing: conflicts`.

## 1. Tests (pr-tests)

- [x] 1.1 Migrate every direct caller of `BindingCheck.conflicts` in the tests to
      `conflicts(passes, moves=None)`, which yields one conflict list per pass:
      - `test_conflict_narrowing.py`, including `_check` users and
        `test_a_run_moving_files_re_judges_every_file`, the single-pass regression with `moves`;
      - `test_rename_bindings.py` (around lines 257–310).

      Same assertions, new call shape. Verify: they fail today only on the signature.
- [x] 1.2 Align `test_conflict_narrowing.py::test_the_all_together_pass_reuses_each_single_entry_state` to one
      `conflicts([[first], [second], [first, second]])` call. It still asserts the all-entries pass parses no
      after-state again. Verify: fails today on the signature.
- [x] 1.3 Liveness, `test_conflict_narrowing.py`. Files: `a` (edited only by entry 1), `b` (only entry 2), `c` (both,
      different edits). Weak references to the after-states are taken as they are built and checked while each
      pass judges (hook `_Judge.conflicts` or equivalent):
      - while pass 2 judges, entry 1's state of `c` is dead and its state of `a` is alive;
      - the all-entries pass builds only `c`'s state.

      Verify: fails today.
- [x] 1.4 Two single-entry passes whose binding edits for one file are identical build that state once (parse
      count). Verify: passes today through the cache, and pins it.
- [x] 1.5 A plan without the all-entries pass, as `check_names` uses when a map conflict exists: no after-state
      outlives its pass. Use weak references, checked during the next pass. Verify: fails today.
- [x] 1.6 Slim states, `test_rename_bindings.py`: build `_Parsed` from a fresh `SourceFile`, weak-reference its tree
      and a few of its nodes, drop the `SourceFile`, and assert every reference is dead (after `gc.collect()`).
      Cover a before-state (`BindingCheck._analyse_before`) and an after-state (`BindingCheck._state`), each from a
      fresh source. Verify: fails today.
- [x] 1.7 Order kept, `test_rename_map.py` or `test_conflict_narrowing.py`: the generator yields pass k's
      conflicts before it builds any state that only pass k+1 reads. Example: a later pass whose edited text
      does not parse (`refactor.cannot-rename`) is not reached while the caller still consumes pass k. Verify:
      fails today on the signature.
- [x] 1.8 Codex review of the tests against this plan (`reviewers.codex`). Verify: findings resolved with the user.

## 2. Implementation (pr-implement)

- [x] 2.1 `bindings.py`: `BindingCheck.conflicts(passes, moves=None)` as a generator.
      - Build each pass's plan up front: names, pattern, `by_file`, `binding`, `changed`.
      - A pass's keys are its after-world's edited modules. Record each key's last reading pass.
      - Judge each pass from its plan, then drop the states whose last reading pass it was, then yield.
      - A pass with no names yields `[]` and reads nothing.

      Verify: tests 1.1–1.5 and 1.7 pass.
- [x] 2.2 `bindings.py`: `_Parsed` keeps `scope` and `all_names` instead of `module`. Update `module_binding`,
      `World._module_meaning` and `World._exports`. Verify: test 1.6 passes.
- [x] 2.3 `rename_map.py`: `check_names` builds the pass list, calls `conflicts` once, and zips each yielded list
      with that pass's `MemberCheck` result inside the existing loop. `rope_refactor.py` passes `[entries]` and takes
      the first yielded list. Verify: `test_rename_map.py`, the `rope_refactor` rename tests and
      `test_refactor_progress.py` pass.
- [x] 2.4 Local test scope (per `/la:pr`) plus the conformance corpus through the Python twin, then
      `uv run ruff check src tests` and `uv run basedpyright src tests` in `python/`, `la-typecheck` and
      `la-arch-check`. Verify: all green.

## 3. Measurement (pr-implement)

- [x] 3.1 Cold DEV-1607 run (0.2) under `/usr/bin/time -v`, alone, on the commit before this change's code and on
      this change: peak RSS, phase split, total. Verify: peak at most 4.3 GB (prototype 3.96 GB) and
      `conflicts` at most about 104 s (prototype 87 s). Results go in a comment on DEV-2317, together with the
      machine's free memory and swap at the time.
- [x] 3.2 Differential: both runs' stdout and their refusal reports (stderr without the `[...]` progress and
      `timing:` lines) are byte-identical. Verify: `diff` output recorded in the same comment.

## 4. Docs

- [x] 4.1 No user-facing doc names the after-state cache or `_Parsed`. Check with
      `grep -rn "after-state\|_Parsed" docs plugin README.md` and record the result. Verify: no hit, or each hit
      updated.
