## Why

`la-arch-check`'s spec-mapping check counts a spec group as present only under `openspec/specs/`, where a new
capability lands only at `openspec archive`, the last step of the `/la:pr` flow. A change that adds a capability
therefore fails the gate at every point: `spec-mapping.dir-missing` if it maps the group during the change,
`spec-mapping.unmapped` after archive if it does not.

## What Changes

- The spec-mapping check takes its present spec groups from `openspec/specs/` and from the `specs/` folder of
  every non-archived change under `openspec/changes/` (everything except `openspec/changes/archive/`). One
  set feeds all three checks: `unmapped`, `dir-missing` and `no-spec-md`.
- `no-spec-md` fires only when none of a group's directories holds a `spec.md`.
- The `spec-mapping.unmapped`, `spec-mapping.dir-missing` and `spec-mapping.no-spec-md` texts no longer name
  `openspec/specs/{group}` as the only location.
- Both twins, new conformance cases, and the `la-arch-check` summary in the living-architecture skill.

## Capabilities

### New Capabilities

### Modified Capabilities
- `arch-check`: spec groups in a non-archived change count as present for spec-mapping.

## Impact

- `python/src/living_architecture/archcheck/docs.py`, `node/src/archcheck/docs.ts`.
- `shared/findings.yaml` (three templates) and the twins' vendored snapshots; goldens of every case printing
  one of those findings.
- `conformance/cases/` (seven new cases), `conformance/INVENTORY.md`.
- `plugin/skills/living-architecture/SKILL.md`.
