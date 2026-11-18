## Why

On main (with DEV-2317's conflict check and DEV-2310's rope-free renames), the DEV-1607 rename map (158 entries,
`--docs`) peaks at 3.74 GB, and the 2,272-entry DEV-2318 map at 9.84 GB. A `rename-map` run keeps every phase's state until the run ends,
because state lives as long as the object owning it rather than until its last reader, and each entry holds its own
copy of the findings it shares with every other entry renaming the same old name.

## What Changes

- In the Python twin, each rename's worker yields a result when its old-name group finishes: what the later phases
  read, nothing more. The phases after `rules` take only results, so a group's working state dies with the group.
- The run holds each leftover finding once per site, not once per entry.
- The `rules` phase's working state ends with it: the occurrence index (its cache saved then) except the class facts
  the name checks read, the type facts, the entry locator, the text tables, the files read from outside the project,
  and the snapshot's parsed forms. The snapshot keeps each file's bytes and text, and later phases parse again what
  they read.
- Output is unchanged.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

None. No spec-level behaviour changes: the conformance corpus pins the output, and the change sets
`skip_specs: true`.

## Impact

- `python/src/living_architecture/refactor/rename_map.py`: `RenameMap`'s phases, the leftover store, the end of
  `rules`.
- `python/src/living_architecture/refactor/rename_union.py`, `literal_rename.py`, `retarget.py`: the workers yield
  results; `MapRename` and the new result type.
- `python/src/living_architecture/refactor/python_project.py` and `rename_union.py`: `Snapshot` and `Session` drop
  parsed forms.
- `python/src/living_architecture/refactor/occurrence_index.py`: the class-fact source the name checks read after
  `rules`.
- `test_refactor_progress.py`'s keyed case patches the keyed check on its new owner, the result type.
- The npm twin is not touched: it already holds leftovers once per old-name group.
- Expected (prototype, warm): the DEV-1607 map peaks at about 2.84 GB, the 2,272-entry map at about 3.91 GB.
