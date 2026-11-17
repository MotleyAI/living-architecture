## Why

DEV-2315 made the DEV-1607 rename map (158 entries, `--docs`) about 4× faster, but its peak memory went from
4.31 GB to 8.49 GB (both re-measured, each run alone on the machine). The conflict check holds every after-edit
module state it builds for the whole run, and each state keeps its whole syntax tree, though only a small part of
it is read after construction.

## What Changes

- The Python twin's binding check takes the whole pass plan at once and keeps each after-edit module state only
  until the last pass that reads it. The cross-pass reuse that DEV-2315 relies on stays.
- A parsed module state keeps only the data the check reads, not its syntax tree.
- The single rename and the rename map run the check through the same pass-plan entry point; output is
  unchanged.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

None. No spec-level behaviour changes: the conformance corpus pins the output, and the change sets
`skip_specs: true`.

## Impact

- `python/src/living_architecture/refactor/bindings.py`: `BindingCheck.conflicts`, `_Parsed`, `World`.
- `python/src/living_architecture/refactor/rename_map.py`: `RenameMap.check_names`.
- `python/src/living_architecture/refactor/rope_refactor.py`: the single rename's call.
- Tests that call `BindingCheck.conflicts` directly move to the new signature.
- The npm twin is not touched: its name checks build their state inside each pass.
- Expected on the DEV-1607 map: peak about 3.9–4.0 GB (prototype: 3.96 GB), `conflicts` phase about 87 s (now
  101 s).
