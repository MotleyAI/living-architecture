## Why

`dr-refactor move-module` and `move-symbol` (rope's `MoveModule`/`MoveGlobal`) rewrite far more than the moved
references. In SLayer's `slayer/sql/client.py` → `slayer/database/` dry-run about ten files changed beyond the path
rewrites. `importorskip`-gated imports were hoisted above their gate (a missing optional driver then fails collection
instead of skipping). Import blocks were reordered, and an untouched from-import was split. A function-local import was
left stale while a module-level one was added. A still-valid chain through another module was rewritten. A self-aliased
import (`import a.b.mod as mod`) crashed the move outright. Neither the formatter nor the type-check gate sees any of
this.

## What Changes

- Python `move-module` and `move-symbol` are computed by one edit planner: rope only finds and resolves the
  occurrences, and the planner turns each into a minimal edit at its exact position. Rope no longer re-writes import
  blocks from scratch or turns every reference into its fully-qualified dotted form.
- An import naming the old path is rewritten in place, keeping its alias, bound names, relative form, comments and
  layout. A from-import is split only when exactly one of its names moves, and the moved name gets a new statement on
  the next line.
- A use whose binding survives the move is untouched. A use whose binding breaks (a submodule reached as a package
  attribute, a moved symbol reached through its old module or a star import) is rewritten, and gets one adjacent
  import.
- A self-aliased import of the moved module moves cleanly instead of crashing.
- A move that would need an import or a binding under a name that already refers to a different object at that scope
  is refused with a located finding, and nothing is written.
- `rename` keeps rope's edits, which are already minimal; fixtures pin them. The TypeScript twin is already minimal;
  fixtures pin it too.

## Capabilities

### New Capabilities

### Modified Capabilities
- `refactor`: adds "Refactors edit only at references" (both languages) and "Python moves rewrite each reference
  minimally", which states the Python edit rules and the name-conflict refusal.

## Impact

- Python twin: `python/src/living_architecture/refactor/` (new edit planner; `rope_refactor.py` routes `move-module`
  and `move-symbol` through it).
- `shared/findings.yaml`: one new `refactor.*` template for the name-conflict refusal; re-vendored into both twins
  (new contract hash).
- Conformance: new Python and TypeScript adapter cases (`golden: manual`), listed in `conformance/INVENTORY.md`.
- Python unit tests for the planner.
- No CLI surface, config key, schema or dependency change.
