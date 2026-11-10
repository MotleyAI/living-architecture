## Why

A duplicate mapping key in `living-architecture.yaml` or `architecture/index.yaml` silently drops data: the shared
YAML profile copies PyYAML's last-wins rule, and no command reports it. A clean git merge that adds the same
top-level key on two branches is enough (e.g. a second `cross_cutting_specs:` made a spec mapping vanish). On top
of that, the readers surface YAML errors inconsistently: `la-arch-check` omits the file, the c4 readers drop the
detail, the npm TypeScript refactor workspace swallows the error, and `la-arch-migrate` migrates past an unusable
index.

## What Changes

- **BREAKING**: the shared YAML profile refuses a duplicate mapping key, at any depth, in both twins: a mapping whose
  loaded value cannot hold two of its keys is invalid YAML. Key identity is defined by the contract (strings and
  timestamps by their normalized string, numbers by exact value with booleans as `0`/`1`, every NaN equal); a
  second merge key in one mapping is a duplicate. Merge overrides stay legal.
- The error names the key and both lines, worded by a new contract template `yaml.duplicate-key`.
- Every reader names the file and carries the duplicate error to the user:
  - the config loaders, unchanged (`<path>: invalid YAML: …`);
  - `la-arch-check` prefixes `architecture/index.yaml: ` to every index YAML error;
  - the c4 index reader (`la-arch-diagrams`, `la-arch-scaffold`, `diagrams-fresh`) reports a duplicate with the new
    template `c4.index-duplicate-key`;
  - the npm TypeScript `dr-refactor`, `dr-compliance` and `dr-mock-lint` fail on an existing `index.yaml` that is
    not UTF-8 or not valid YAML instead of falling back to another tsconfig;
  - `la-arch-migrate` refuses (exit 2, nothing written) an existing `index.yaml` that is not UTF-8, not valid YAML
    or not a mapping when it converts a model, instead of migrating past it.
- The contract text (`shared/README.md`), the shared YAML vectors and the duplicate-key conformance golden flip
  from last-wins to refusal.

## Capabilities

### New Capabilities

### Modified Capabilities
- `shared-contract`: the YAML profile refuses duplicate mapping keys, and every reader reports one naming the file,
  the key and both lines.
- `refactor`: the TypeScript commands fail on an existing `index.yaml` that is not valid YAML instead of falling
  back.
- `c4-layout`: `la-arch-migrate` refuses an existing but unusable `index.yaml` when it converts a model.

## Impact

- Both twins' YAML profile (`python/src/living_architecture/contract/yaml_profile.py`, `node/src/contract/yaml.ts`)
  and their index readers (`archcheck`, `c4`, `c4` migrate, npm `refactor/workspace.ts`).
- `shared/`: `README.md`, `findings.yaml` (two templates), `vectors/yaml.yaml` (new `error: duplicate` kind); both
  twins' vector runners.
- Conformance corpus: flipped and new cases, `INVENTORY.md`.
- Repos with a duplicate key in either config file stop loading until it is removed. No format change; the next
  release is a minor bump because `shared/` changes.
