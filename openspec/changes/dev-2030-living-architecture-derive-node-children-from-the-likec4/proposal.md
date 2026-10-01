## Why

`architecture/index.yaml` `nodes:` duplicates the LikeC4 model: node ids must equal top-level element ids,
`children:` must equal each node's model children, and `virtual:` must equal the element kind's `#virtual`.
The duplicates are kept in sync by `model-identity` findings. The model should be the only source for
elements, nesting, arrows and the element-to-code mapping, and `index.yaml` should keep only repo-wide
settings.

## What Changes

- **BREAKING** A node (a top-level model element) declares its code mapping and doc/spec pointers in a
  LikeC4 `metadata { }` block: `package` (required) and `claims` for a precise node, `packages` for a virtual
  node, and `arc42` / `specs` for either. Metadata is validated strictly against a new shared node schema.
- Nested elements, at any depth, carry no metadata and map by convention: `<node>.a.b` → `<node package>.a.b`.
  The import law applies wherever the model nests. Elements under a virtual node are not mapped.
- **BREAKING** `nodes` is removed from `index.yaml` and its schema; a file that still has it is a setup error
  naming the key. `index.yaml` keeps `root_package`, `source_root`, `cross_cutting_arc42`,
  `cross_cutting_specs`, `legacy_arrows`, `diagrams`, `view_depth`.
- Malformed metadata (syntax, a repeated key, a second block, a schema violation, metadata on a nested
  element) is a setup error (exit 2) in `la-arch-check`; bad metadata syntax is a parse finding in
  `la-arch-diagrams`.
- **BREAKING** Findings: the `model-identity` check and its three findings are removed (impossible by
  construction), as is `claims-exactly-once.child-twice` (the parser reports duplicate elements).
  `claims-exist.child-missing`, `claims-exactly-once.child-collides` and `claims-exist.virtual-children` are
  reworded for model-derived elements of any depth.
- This repo's own model and `index.yaml` migrate; the `living-architecture` and `arch-slice` skills and the
  README document the new format plus a manual migration procedure (no migration command).

## Capabilities

### New Capabilities

### Modified Capabilities
- `arch-check`: node mapping moves into model metadata; child units derive from model nesting at any depth;
  the source-root requirement's wording follows.
- `shared-contract`: node metadata keys and types come only from the shared node schema; the index schema no
  longer defines nodes.

## Impact

- `shared/`: `schema/index.schema.json`, new `schema/node.schema.json`, `findings.yaml`; every twin snapshot
  via `scripts/sync-shared` (contract hash changes).
- Python twin: `c4/model.py` (metadata parsing), `archcheck` (canonical node/unit map, claims, docs, truth,
  `license()`; `check_model_identity` and the `children` logic removed).
- Conformance: every fixture and case migrates `nodes:` into model metadata; goldens change only where
  behaviour changes; `INVENTORY.md`.
- `architecture/model/la.c4`, `architecture/index.yaml`; `plugin/skills/living-architecture`,
  `plugin/skills/arch-slice`, `README.md`.
- Target repos must move `nodes:` into model metadata once.
