## Why

`dr-refactor rename` and `rename-map` write code whose names mean something else, and exit 0. A rewritten reference is
captured by an inner binding of the new name (`return old + next` becomes `return next + next`), an existing reference is
shadowed by the renamed declaration, a member lands on a name its class (or an ancestor or descendant) already declares,
and a Python module rename overwrites an existing module. Each twin has a few partial, hand-written conflict checks, each
re-implementing a slice of name resolution, so every shape they miss is a silent miscompile.

## What Changes

- Both twins refuse a rename (and every `new_name` entry of a map) with the existing `refactor.name-conflict` finding when
  it changes which declaration any reference resolves to: a captured rewritten reference, a shadowed existing reference
  (builtins and globals included), a new name its scope already binds, or a kept `--keep` site that would rebind.
- Both twins refuse a member rename when the member's type, any ancestor (library and implicit root included) or any
  project descendant declares a member of the new name on the same side.
- The Python twin refuses a module or package rename onto a name its package already binds.
- One binding-preservation check (names re-resolved over the edited code) plus one member-namespace check replace the
  existing partial checks: the TypeScript declaring-scope check, both twins' map convergence checks and the Python
  parameter conflict scan. The Python parameter rule is relaxed accordingly: a nested binding of the new name that
  changes no reference's meaning is no longer a conflict.
- Name conflicts are checked after `--keep` and before the blind-spot refusal; a map is checked entry by entry against
  the code before the map, then as a whole.
- `shared/languages.yaml` gains the Python implicit root class's member names.

## Capabilities

### New Capabilities

### Modified Capabilities
- `refactor`: renames refuse a new name that changes a reference's binding or collides with a member; map conflict
  checks run per entry and combined; Python parameter conflicts follow binding preservation; Python module renames
  refuse an existing destination.

## Impact

- `node/src/refactor/rename.ts` (and a new resolver module beside it), `python/src/living_architecture/refactor/`
  (`rename_map.py`, `rename_union.py`, `rope_refactor.py`, a new binding module), `shared/languages.yaml` and its twin
  snapshots.
- Conformance: new paired and adapter cases under `conformance/cases/`, `conformance/INVENTORY.md`.
- Tests: one existing unit test (`test_type_parameter_of_the_new_name_is_a_conflict[nested]`) aligned to the relaxed
  parameter rule.
- No model, arc42 or finding-text change.
