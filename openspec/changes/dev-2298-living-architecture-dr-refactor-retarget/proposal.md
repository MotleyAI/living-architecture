## Why

`dr-refactor retarget` refuses a target that the alias's module imports (`refactor.retarget-scope`), so SLayer's real
back-compat map — `slayer/flight/catalog.py` declaring `FlightCatalog = FacadeCatalog` of a name imported from
`slayer.facade.catalog` — cannot run. And a retarget can still write an unbound name: a star import from a
single-name shim (`from pkg.compat import *`) and an attribute access through the shim module
(`pkg.compat.AcmeModel`) are rewritten to the target, which nothing binds there (DEV-2295's decision 48 left these).
Both twins behave this way.

## What Changes

- `retarget` accepts a target the alias's module imports (`ALIAS = TARGET` of an imported name, or a re-export
  `from M import T as ALIAS` / `export { T as ALIAS } from 'M'`); a member alias still needs its target in its class.
- Every rewritten reference is judged by one rule: the written name resolves to the target after the edit, already
  bound or bound by an import the retarget adds from the target's home (the module the alias's module imports it
  from). An import of the alias is re-pointed to the target's home.
- Only re-export sites keep the alias: an `__all__` string naming it and the import or export re-exporting it. A
  shim's own uses of the alias and the modules importing it through a shim are now rewritten, with the target
  imported. **BREAKING** for decision 48's "a reference that a kept re-export binds stays".
- A module attribute `MOD.ALIAS` whose module does not bind the target refuses with a new
  `refactor.retarget-unbound` finding (exit 1).
- A `retarget-shadowed` or `retarget-unbound` refusal on a line `--keep` covers no longer blocks the refactor.
- The `deterministic-refactor` skill and `docs/deterministic-refactoring.md` describe the imported target.

## Capabilities

### New Capabilities

### Modified Capabilities
- `refactor`: the requirement "Retarget rewrites references to an alias" is replaced by "Retarget rewrites
  references to an alias and keeps every name bound" — imported targets, the bound-name rule with import insertion,
  re-export sites only, the unbound-attribute refusal and `--keep` on retarget refusals.

## Impact

- `shared/findings.yaml` (`refactor.retarget-unbound`), synced into both twins' snapshots.
- Python twin: `refactor/retarget.py`, `refactor/rename_map.py` (target resolution, import planning across entries,
  `--keep` before import planning).
- npm twin: `src/refactor/rename.ts` (the same).
- Conformance: new paired cases; `refactor-map-retarget-single-name-shim`, `refactor-map-retarget-reexport-shim` and
  `refactor-retarget-scope` change; `conformance/INVENTORY.md`.
- `plugin/skills/deterministic-refactor/SKILL.md`, `docs/deterministic-refactoring.md`.
- No architecture model, arc42 or CLI-surface change.
