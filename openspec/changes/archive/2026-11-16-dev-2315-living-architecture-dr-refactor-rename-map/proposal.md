## Why

A cold dry run of the DEV-1607 rename map (158 entries, `--docs`, 279 site flags, 1,600 Python files) takes
32 min 31 s after DEV-2301. Profiling shows four independent causes, all work repeated that depends on less than the
loop it sits in. (A fifth, the export following definitions into library code, is fixed by DEV-2307.)

## What Changes

- The language-server client reads each message in time linear in its size (the 103 MB export answer took about
  360 s to read).
- `dr-refactor`'s language server runs no ambient analysis of opened files.
- Rule scans whose result depends only on a file and an old name run once per run, not once per entry.
- The conflict checks re-parse and re-judge only the files an entry's edits can change the meaning of.
- A new `conflicts` phase: the checks made over a run's computed edits (map conflicts and name conflicts) announce
  themselves with `[conflicts]` and have their own `--timings` line, in both twins.
- The DEV-1607 map is re-timed cold and warm, and the numbers recorded on the issue.
- A rename map no longer lists, as one entry's leftover, a string another entry rewrites.

Stdout, refusals and exit codes are unchanged; the observable changes are the `conflicts` phase and the leftovers a
map no longer lists at another entry's rewrites.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `refactor`: the phase list of `--timings` and of the announced phases gains `conflicts`, between `rules` and
  `baseline`; a rename map lists no leftover at a site another entry rewrites.

## Impact

- Python twin: `lang/language_server.py`, `lang/pyright_export.cjs` (the ambient-analysis anchor), `refactor/` (`rename_map.py`, `rename_union.py`,
  `keyed.py`, `bindings.py`, `member_namespace.py`, `rope_refactor.py`, `occurrence_index.py`, `timings.py`).
- npm twin: `node/src/refactor/rename.ts` and its timings.
- `shared/cli.yaml` (`timing_phases`), then `scripts/sync-shared`.
- Conformance goldens of every `rename`, `retarget` and `rename-map` case that reaches the conflict checks: one
  added stderr line each.
- Tool inputs change, so the next release raises the minor version.
