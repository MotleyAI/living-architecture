## Context

See proposal.md for why. The current shape (main after DEV-2310 and DEV-2317), in
`python/src/living_architecture/refactor/`:

- `RenameMap` keeps `self.session` (the snapshot, which caches a parsed `SourceFile` per file read, plus the text
  tables and the files read from outside the project), `self.index` (`RunIndex`), `self.server` and `self.locator`
  (`EntryLocator`) for the whole run; `run` keeps the `renames` list (one worker per entry: `SymbolRename`,
  `AliasRetarget`, `LiteralRename`) until it returns. `seed` makes a `TypeFacts`, a local of `run`.
- `rules` processes old-name groups in order of their first entry: each live rename's rules, then `_finish` (finish,
  merge, retarget, `_keep`), then the group's refusals. After the last group, `_imports` plans every retarget's
  `ImportNeed`s at once (`plan_imports`) and appends the imports to the owning entries' edits. `run`'s `finally`
  then closes the server and the index (saving the export cache).
- After `rules`, the run reads from a worker only: `old`, `new`, `header()`, `member`, `edits`, `imports` and `held`
  (retargets), `blindspots`, `stand_in_findings()` (from `_unclassified` and the run's `is_renamed`), `refusals`
  (retargets), `matched_sites`, `leftovers`, `unresolved`, `renamed_members()` (from `_declarations` and the
  snapshot) and `check_conflicts(edits)` (the snapshot).
- After `rules`, the run reads from the index only class facts: `check_names` builds `Hierarchy(..., self.index)`,
  which calls `class_facts` for a renamed member's class and for each class declaring a new name. `prepare` requests
  them for the candidate files and the files spelling an entry's `new_name`, so most are merged already. An
  NFKC-equivalent spelling of a new name, in either direction, can miss; a retarget never asks one, as it renames no
  member declaration. A miss exports that one fact: the
  cache cannot hold it (it is saved in `run`'s `finally`, before `conflicts`, and anything `rules` asked for is
  merged), so it goes to `ServerSession.get()`, which starts a fresh language server, as `finally` closed the run's.
- `ImportNeed` holds AST nodes (`anchor`, `leaving`, `duplicates`).
- A module rename is a map entry: `ModuleRename` prepares its edits and move in `references`; after `rules` the run
  reads its move, module, package flag, the stub and the move conflicts.
- `findings()` prints the keys of `{(path, line, col, text): f}` built from every rename's leftovers that no final
  edit covers (`col`, else `col:end`), then the undecodable files' findings and every `unresolved` finding. Only
  `text` is printed, so a leftover key is printed iff some copy of it is uncovered.
- `_keep` filters edits, blind spots and `unresolved` with `keeps.kept(...)`, which marks the keep matched, and
  leftovers with `mark=False`, which does not.

Measured at the start of `conflicts` on main (bytes each holder alone keeps alive: everything reachable from the run's
roots, minus what stays reachable with that holder cut), warm export cache:

| Holder | DEV-1607 map (158 entries) | DEV-2318 map (2,272 entries) | Why it is that large | Read after `rules` |
|---|---|---|---|---|
| Renames' `leftovers` | 366 MB | 5,040 MB | Held per entry. The 2,272 entries have 853 old names (`model` in 353), about 60k unique findings. Each `Finding` is a pydantic model with a `__dict__` and a fields-set `set` (3.3 GB of sets). | Yes, once per site suffices |
| Renames' `_examined` | 50 MB | 720 MB | Each entry's examined spans per file | No |
| Renames' `edits`, `_graph`, `_files` | 69 MB | 122 MB | | Edits only |
| `RunIndex` | 922 MB | 1,079 MB | Occurrences (430–485 MB) and facts (272–306 MB) as pydantic models, with strings repeated per occurrence; the per-file rule memo (145–273 MB) | Class facts only: 4,788 of 54,310 positions, about 96 MB shared with the rest (41 MB on DEV-2318) |
| Snapshot's parsed `SourceFile`s | 566 MB | 433 MB | AST nodes, each with its own `__dict__`; `_definitions` (120–193 MB) and `_parents` (about 90 MB) derived caches | Tree, `nodes`, `of_type`: yes. `_definitions`, `_parents`: no |
| `session.tables` | 83 MB | 83 MB | Per-file word and region tables | No |
| Files read from outside the project | 33 MB | 88 MB | Parsed library sources | No |
| `EntryLocator` | 32 MB | 43 MB | Static-resolver modules and scopes | No |

RSS at the start of each phase (DEV-1607 / DEV-2318, warm): `references` 1.86 / 1.09 GB, `rules` 2.07 / 2.45 GB,
`conflicts` 3.09 / 8.92 GB. Re-parsing every parsed file takes 1.7 s.

Runs on main and a monkeypatched prototype (leftovers once per site; the `rules` working state dropped when `rules`
ends, keeping only the index's class facts, where a miss is logged):

| Run | Peak RSS | Total | Output |
|---|---|---|---|
| DEV-1607 main, cold | 3.74 GB | 448 s | |
| DEV-1607 prototype, warm | 2.84 GB | 310 s | byte-identical, no class-fact miss |
| DEV-2318 main, cold | 9.84 GB | 1,086 s | |
| DEV-2318 prototype, warm | 3.91 GB | 712 s | byte-identical, no class-fact miss |

The prototype released the workers' state only at the end of `rules`, so its peak sits at the end of `rules`.

## Goals / Non-Goals

**Goals:**

- State lives until its last reader: no worker, `RunIndex` (beyond its class facts), `TypeFacts`, `EntryLocator`,
  text table, outside file or parsed snapshot form survives `rules`, and a group's working state dies when the group
  finishes.
- Each leftover finding is held once per site.
- The DEV-1607 map peaks at or below 3.0 GB and the DEV-2318 map at or below 4.0 GB; total time no slower than
  main's.
- Output is byte-identical: stdout, the refusal report and the printed findings.

**Non-Goals:**

- A slimmer `RunIndex` representation (compact occurrences and facts instead of pydantic models). (user)
- The npm twin: it already holds leftovers once per old-name group, and nothing observable changes.
- Moving any work between `--timings` phases: the keyed name check stays in `conflicts`.

## Decisions

1. **Worker → result.** Each worker yields a result, a `BaseModel` holding exactly what the run reads after `rules`:
   entry position and map indexes, `old`, `new`, the header, the member flag, whether it checks names, final edits,
   held edits, imports, blind spots, `unresolved` findings, stand-in findings (evaluated at conversion, when the
   run's `is_renamed` is final), retarget refusals, matched sites, and its member declarations. A result holds no AST
   node and no `SourceFile`, so no `ImportNeed` either. Site resolution, the report, the name checks, the findings and
   the outputs take only results. A module rename's result, `ModuleResult`, also holds its module, its move and
   whether it is a package; the moves, the stubs and the move conflicts read those.
   - Rejected: a `release()` protocol emptying each worker's working fields. Every future working field would have
     to be added to it by hand, or it silently survives: the bug class stays open. (user)
2. **Results are made as each group finishes.** After a group's `_finish`, its workers become results and the run
   drops them, so a group's `_examined`, `_targets`, `_graph`, `_parents`, `_index` and locator reference die with it.
   A retarget's `ImportNeed`s go to a side list for the run instead. The import plan runs once over that list after
   the last group, appending each import to the owning result's edits, as `_imports` does today (per-group planning
   would change how imports combine and which entry owns them); the list is dropped then, before the parsed forms
   are. (default; global import pass and AST-holding needs from codex)
3. **One step ends `rules` on every path.** It runs after the last group, and also when `rules` is skipped or
   stopped (a `--fail-fast` stop in `references` or `rules`): every worker not yet converted becomes a result as it
   stands, with no `finish`, retarget, import or keep work done for it; then the `rules` working state is released.
   So every entry, including a failed one, one whose new name equals its old one, and one never reached, yields a
   result. A module rename ends `rules` the same way. (codex)
4. **The `rules` working state ends with `rules`, except the class facts.** The step of decision 3 closes the
   `RunIndex` (saving the export cache, as `run`'s `finally` does today, which still closes it on any failure) and
   the run's `ServerSession`, and keeps of the index only a class-fact source for `conflicts`: the `class` facts
   merged so far, and on a miss one export of that fact, with the run's member names, as `RunIndex._fact` does,
   through the run's `ServerSession`, which starts a fresh language server as it does today; `run_map`'s `finally`
   closes it. The occurrences, the other facts, the rule memo and the cache's entries die. So do `TypeFacts`,
   `EntryLocator`, `session.tables`, the files read from outside the project and the snapshot's parsed `SourceFile`s.
   The snapshot keeps each file's bytes, encoding and text, and later phases parse again what they read (about 1.7 s
   for every file).
   - Misses are expected (an NFKC-equivalent spelling of a new name, in either direction). They skip the cache, which cannot hold them
     today either, so the answer, the server's lifecycle and a server failure's refusal stay as they are. `prepare`
     is not widened to request them: that would change the export request and its cache keys. Neither prototype run
     missed. (default; misses and server lifecycle from codex)
   - Rejected: dropping only `_definitions` and `_parents`. It needs a hand-kept list of which caches later phases
     read, and keeps trees of files no later phase reads. (default)
5. **Leftovers are held once per site.** One run-wide store maps `(path, line, col, text)` to the distinct `end`s
   seen for it. A leftover enters it after the keeps filter it with `mark=False`, exactly as `_keep` does today.
   `findings()` prints a leftover key iff some stored span (`col`, else `col:end`) is not covered by a final edit,
   merged with the undecodable and `unresolved` findings and printed in key order, exactly as today. (default; `end`
   semantics from codex)
6. **The keyed name check and the renamed members stay in `conflicts`.** They are computed there from results and
   the snapshot, so `--timings` still charges them to `conflicts`, as `test_refactor_progress.py` pins. (default)
7. **Tests use weak references and counts, not peak memory.** Peak memory is not deterministic in a suite, so it is
   measured by hand on both maps. (default)
8. **No spec delta.** `skip_specs: true`: the output does not change. (default)
9. **Lifetime only.** The `RunIndex` keeps its representation; slimming it would change the `lang` models and maybe
   the cache format, and needs its own prototype. (user)
10. **The npm twin is out of scope.** It holds leftovers once per old-name group already. (default)
11. **Measured on main.** Merging main (DEV-2310's rope-free renames) moved the class hierarchy onto the index's
    class facts; the investigation was redone on main, and before is main at the merge. (default)

**Architecture.** System principles 1 (twins: the corpus decides; no output changes), 2 (no new parameter or text)
and 3 (language-specific code stays in `refactor`) apply. The result type and the class-fact source live in
`refactor`; no model element or arrow changes.

## Risks / Trade-offs

- [A later phase reads a worker field the result lacks.] → The result is a separate type: such a read fails the
  type check, not silently at run time.
- [Results change output through ordering or dedupe.] → The leftover store keeps every distinct `end`; the import
  plan stays one global pass; the corpus and the differential runs on both maps pin the output.
- [A class fact misses after `rules`.] → It is exported through the run's `ServerSession` as today; tests pin a
  miss in each NFKC direction and a server failure on a miss.
- [Re-parsing in `conflicts` costs time.] → About 1.7 s for every file; the prototype's DEV-1607 `conflicts` took
  97 s against main's 101 s.
- [An object a result holds keeps a tree alive.] → Results hold no AST node or `SourceFile`; the liveness tests
  check that no parsed snapshot form survives `rules`.
- [Timings drift with machine load.] → Measure alone, cold, and record the machine's state with the numbers.
