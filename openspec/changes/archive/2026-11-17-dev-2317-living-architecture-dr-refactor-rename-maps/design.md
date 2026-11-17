## Context

See proposal.md for why. The current shape, in `python/src/living_architecture/refactor/bindings.py`:

- `RenameMap.check_names` runs one binding pass per `new_name` entry, then (when no map conflict exists) one pass
  with every entry, and pairs each pass with a `MemberCheck` pass. `rope_refactor` runs one pass, with `moves`.
- `BindingCheck._state` caches each after-edit module state, keyed by `(module, file, binding edits)`, for the
  life of the `BindingCheck`. A pass's after-world builds a state only for its edited modules: the files with
  binding edits, plus the moved files.
- `_Parsed` holds `module = Module(tree, ...)`, whose `binder` keeps AST nodes (`bound`, `loads`, `annotations`,
  `decls`, `class_nodes`, `star_nodes`). After construction, only `module.scope` and `module.all_names` are read.

Measurements on the DEV-1607 map (each run alone, warm export cache unless noted; stdout and refusal report were
byte-identical across every variant):

| Run | Peak RSS | `conflicts` |
|---|---|---|
| Before DEV-2315 (`c775d394`, cold) | 4.31 GB | none: that version refuses on a false name conflict |
| HEAD (cold) | 8.50 GB | 261 s, a run contended by another job and full swap; discarded |
| HEAD | 8.49 GB | 101 s |
| Prototype: liveness only | 5.05 GB | 100 s |
| Prototype: slim states only | 4.88 GB | 84 s |
| Prototype: liveness + slim states | 3.96 GB | 87 s |
| Prototype: + NFKC-folded `may_name` | 3.89 GB | 98 s |

Other facts measured on that run:
- RSS is 3.2 GB when the check starts, and 3,727 after-states are built, about 1.3 MB each.
- Of 8,421 pass uses of a state, 4,694 are reuses from an earlier pass. 1,081 states are shared between
  single-entry passes, and the all-entries pass reuses 226 of its 909.
- In the profile, `_Parsed` construction is about 70% of the check's time.
- A state's AST is about 75% of its size: 15.6 MB against 3.9 MB for `slayer/sql/generator.py`.

## Goals / Non-Goals

**Goals:**

- The conflict check holds each state only while a later pass will read it, and no state holds its syntax tree.
- The DEV-1607 map peaks at or below 4.3 GB, with `conflicts` at or below about 104 s.
- The check's output and the order of its work are unchanged: binding and member checks still alternate per pass.

**Non-Goals:**

- The state the earlier phases hold: 3.2 GB at the start of `conflicts`, covered by DEV-2323.
- Deriving an after-state incrementally from its before-state.
- The npm twin: it has no state that outlives a pass.

## Decisions

1. **State lifetime follows the pass plan, inside `BindingCheck`.** `BindingCheck.conflicts(passes, moves=None)`
   takes every pass at once. First it computes each pass's plan: names, pattern, and per-file binding edits
   (`merge_edits` plus the inert-span filter, or every edit when files move). A pass's keys are its after-world's
   edited modules, and from those it records each key's last reading pass. Judging consumes the same plans. A
   state is built lazily, once, and dropped after its last reading pass.
   - Rejected: dropping a state once it has been reused, which leaves states no later pass reads alive until the
     end.
   - Rejected: keeping only states of files one entry edits, special-cased in `check_names`, which misses the
     1,081 states reused between single-entry passes.
   - Both rejected options patch one pass plan instead of the cause. (default)
2. **`conflicts` is a generator yielding one pass's conflicts at a time.** `check_names` consumes it in its existing
   loop, so binding and member checks keep their order. An exception from a later pass, such as
   `refactor.cannot-rename`, can't preempt an earlier pass's member check, which may itself raise through rope.
   (codex)
3. **One entry point.** A single rename is a one-pass plan: `rope_refactor` takes the first yielded list. Every
   direct caller moves to the new signature: `rope_refactor.py`, `test_conflict_narrowing.py`, and
   `test_rename_bindings.py`. (default; caller list from codex)
4. **Slim states.** `_Parsed` stores `scope` and `all_names` instead of `module`, so the binder and AST die with the
   constructor. Readers `module_binding`, `World._module_meaning` and `World._exports` change. This goes beyond
   the issue's scope; the user approved it because liveness alone measured 5.05 GB, above the target. (user)
5. **A star-import chain needs no extra plan entries.** It reads another module through the after-world, which
   builds states only for that pass's edited modules, all of them already in the pass's keys. The codex finding
   asking for a reachable-module closure was rejected for this reason. (rejected (codex))
6. **NFKC-folded `may_name` prefilter rejected on measurement.** 1,160 of SLayer's 1,619 files are non-ASCII, so
   `may_name` passes them all. Folding before the prefilter brought peak to 3.89 GB but `conflicts` to 98 s:
   most of those files are edited anyway, and the extra regex scans cost more than they save. (default)
7. **Earlier-phase state goes to a new issue.** The user approved creating DEV-2323 for it instead of widening this
   change: the cause needs investigating before a design. (user)
8. **The cache stays, for a different reason than the issue gives.** The issue's "cache off" run took more than 20
   minutes, but it re-parsed on every lookup within a pass. The cache is kept because of the 4,694 reuses across
   passes. (default)
9. **Tests use weak references and parse counts, not peak memory.** Peak memory is nondeterministic in a suite,
   so it is measured by hand on the DEV-1607 map. The AST-retention test weak-references the tree and some
   nodes, rather than walking `gc.get_referents`, which would also reach classes, functions and modules.
   (default; test shape from codex)
10. **No spec delta.** `skip_specs: true`, because the output does not change. (default)

## Risks / Trade-offs

- [The plan's keys could drift from what a pass reads.] → The plans are computed once, and judging consumes the
  same objects.
- [A planned key is never read: a binding file the pass doesn't judge.] → States are built lazily, so a key that
  is never read is never built. Its plan entry costs nothing.
- [A later reader needs the AST from a parsed state.] → Only `scope` and `all_names` are read today. The slim-state
  test fails if a reader ever brings the tree back.
- [Timings drift with machine load: a contended run took 261 s.] → Measure alone, and record the machine's state
  next to the numbers.
