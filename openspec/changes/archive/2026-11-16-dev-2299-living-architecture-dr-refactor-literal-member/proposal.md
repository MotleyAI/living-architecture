## Why

A Python `Literal` member rename makes every project source a candidate and pulls the checker's diagnostics for all of
them before the probe and again in the verification round: 110 s on SLayer's DEV-1607 branch (DEV-2295 task 12.2),
89 s on a re-run. `dr-refactor` prints no phase times, so task 12.2 could not attribute that time.

## What Changes

- Python twin: a `Literal` member rename asks the checker only about the files it can affect, the reverse import
  closure of the member's file plus every file holding an equal string, and pulls a file's pre-probe diagnostics only
  when a probe round shows that file an error. Output stays byte-identical.
- Python `lang`: import resolution over repo files becomes extension-aware (`.pyi` stubs, `__init__.pyi`, `-stubs`
  directories) and gains the reverse import closure of a file.
- Both twins: a top-level `dr-refactor --timings` option prints each phase's wall time on stderr after all other
  output, from a shared phase list and line template.
- The SLayer `Literal["edit_model"]` dry run is re-timed and recorded on DEV-2299.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `refactor`: the `Literal` member requirement gains scenarios for the import routes a typed string or blind spot
  arrives by; a new requirement for `--timings`.

## Impact

- `shared/cli.yaml` (the `--timings` option, the phase list), `shared/findings.yaml` (`refactor.timing`); every twin's
  vendored snapshot via `scripts/sync-shared`.
- Python: `lang/edges.py`, `refactor/literal_rename.py`, `refactor/rename_map.py`, `refactor/rope_refactor.py`,
  `refactor/baseline_align.py` call sites, the `dr-refactor` CLI, a new timer module in `refactor`.
- npm twin: `refactor/index.ts`, `refactor/typescript.ts`, `refactor/rename.ts`, `refactor/session.ts`, a new timer
  module in `refactor`.
- Conformance: new cases for `--timings` and for the `Literal` import routes; `conformance/INVENTORY.md`.
- Docs: the `dr-refactor` docs mention `--timings`.
- No model or arc42 change: the `refactor -> lang` arrow exists in both twins.
