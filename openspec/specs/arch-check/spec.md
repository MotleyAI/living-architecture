# arch-check Specification

## Purpose
The architecture cross-check: code, the LikeC4 model, arc42 docs and OpenSpec specs agree, and the model is the
repo's single import law. This delta covers where source code is located relative to the repo root.

## Requirements

### Requirement: Source root is separate from the repo root
`architecture/index.yaml` MAY set `source_root`. This is a relative path from the repo root to the directory
that contains `root_package`; when absent it defaults to the repo root. All source discovery SHALL resolve
under `source_root`: claims, model-derived child units, top-level units and import-edge measurement.
Architecture files, arc42 docs and OpenSpec specs SHALL resolve from the repo root. Module ids, and therefore
findings, SHALL NOT include the `source_root` prefix.

#### Scenario: Absent source_root behaves as before
- **WHEN** an `index.yaml` without `source_root` is checked
- **THEN** every finding, stdout line and exit code equals the frozen pre-change golden

#### Scenario: src layout is checked
- **WHEN** `index.yaml` sets `source_root: python/src` and `root_package: pkg`, and the package lives at `python/src/pkg`
- **THEN** claims, top-level units and measured import edges are resolved under `python/src/pkg`, and findings name modules as `pkg.<...>` without the prefix

#### Scenario: Architecture files stay at the repo root
- **WHEN** `source_root: python/src` is set
- **THEN** `architecture/`, the arc42 files and `openspec/specs/` are still read from the repo root

#### Scenario: Invalid source_root
- **WHEN** `source_root` is absolute, contains `..`, resolves (including via symlinks) outside the repo, is not a directory, or does not contain `root_package`
- **THEN** `la-arch-check` exits 2 with an error naming `source_root`

#### Scenario: Invalid root_package
- **WHEN** `root_package` is absolute, has an empty, `.` or `..` segment (e.g. `pkg/`, `.`, `./pkg`), resolves (including via symlinks) outside `source_root`, or is not a directory
- **THEN** `la-arch-check` exits 2 with an error naming `root_package`

### Requirement: Nodes declare their mapping in model metadata
A node SHALL be a top-level element of the LikeC4 model; it is virtual iff its element kind is declared
`#virtual`. A node SHALL declare its code mapping and pointers in one `metadata { }` block in its element body:
a precise node SHALL set `package` and MAY set `claims`; a virtual node MAY set `packages`; either MAY set
`arc42` (a string) and `specs`. Metadata keys and types SHALL be exactly those of the shared node schema, with
no other key allowed. Metadata values SHALL use the subset `key 'value'` or `key ['a', 'b']`: single-quoted
strings without escapes, arrays that MAY span lines, no trailing comma. claims-exist, claims-exactly-once,
arc42-exists, spec-mapping and model-truth SHALL take node ids, units, docs and spec groups only from the
model, and `cross_cutting_specs.touches` SHALL resolve against model node ids.

#### Scenario: Node mapping read from metadata
- **WHEN** the model declares `api = node 'API' { metadata { package 'pkg.api'  specs ['api'] } }` and `pkg.api` exists
- **THEN** `pkg.api` is claimed by `api`, spec group `api` is mapped to `api`, and no finding concerns either

#### Scenario: Virtual node maps buckets
- **WHEN** a top-level element of a `#virtual` kind sets `packages ['pkg.old']`
- **THEN** `pkg.old` is claimed by that node and its modules attribute to it

#### Scenario: Multi-line array
- **WHEN** a node sets `claims` with its array split across several lines
- **THEN** the claims are read exactly as the one-line form would be

#### Scenario: No model files
- **WHEN** `architecture/model/` has no `.c4` file
- **THEN** no node exists, and every top-level unit of the root package is reported as unclaimed

### Requirement: Nested elements map to units by convention
An element nested under a precise node, at any depth, SHALL map to the unit formed by appending its path below
the node to the node's `package` (`<node>.a.b` → `<package>.a.b`) and SHALL carry no metadata. Each such unit
that does not exist under `source_root` SHALL yield `claims-exist.child-missing`. Each such unit that equals,
contains or nests in a unit declared in any node's metadata other than its own node's `package` SHALL yield one
`claims-exactly-once.child-collides`, naming the first such unit in sorted order. A virtual node containing any
element SHALL yield one `claims-exist.virtual-children`, and elements under a virtual node SHALL map to no
unit. Modules SHALL attribute to the finest mapped element, and the import law SHALL apply between mapped
elements at every depth.

#### Scenario: Model child governed with no index entry
- **WHEN** the model nests `handlers` under node `api` (package `pkg.api`), `pkg.api.handlers` exists, and `index.yaml` mentions neither
- **THEN** modules under `pkg.api.handlers` attribute to `api.handlers`, an arrow `api.handlers -> core` covering a measured edge is live, and an unmodelled import from `pkg.api.handlers` to `pkg.store` is reported as `model-truth.missing-edge` from `api.handlers`

#### Scenario: Grandchild governed
- **WHEN** the model nests `x` under `api.handlers` and `pkg.api.handlers.x` exists
- **THEN** modules under `pkg.api.handlers.x` attribute to `api.handlers.x`, and no claims finding concerns it

#### Scenario: Model child missing on disk
- **WHEN** the model nests `inner` under node `core` (package `pkg.core`) and `pkg.core.inner` does not exist
- **THEN** `la-arch-check` reports `claims-exist: element core.inner maps to pkg.core.inner, which does not exist on disk` and exits 1

#### Scenario: Grandchild missing on disk
- **WHEN** the model nests `y` under `api.handlers` and `pkg.api.handlers.y` does not exist
- **THEN** `claims-exist.child-missing` is reported for `api.handlers.y`

#### Scenario: Child collides with another node's claim
- **WHEN** node `core` claims `pkg.api.handlers` and the model nests `handlers` under node `api` (package `pkg.api`)
- **THEN** `claims-exactly-once: element api.handlers (pkg.api.handlers) collides with declared unit pkg.api.handlers` is reported

#### Scenario: Descendants of one node do not collide with each other
- **WHEN** the model nests `x` under `api.handlers` and both units exist
- **THEN** no `child-collides` finding is reported

#### Scenario: Virtual node contains elements
- **WHEN** a virtual node contains one or more nested elements
- **THEN** exactly one `claims-exist: virtual node <node> may not contain elements` is reported, and its nested elements map to no unit

#### Scenario: Virtual-kind element nested under a precise node
- **WHEN** an element of a `#virtual` kind is nested under a precise node
- **THEN** it maps by convention like any other nested element

### Requirement: Malformed node metadata is a setup error
`la-arch-check` SHALL exit 2 with a setup error naming the element when node metadata is malformed: a line
outside the metadata subset, a repeated key, a second `metadata` block, metadata on a nested element, or a node
whose metadata violates the shared node schema (a missing required key, an unknown key, a wrong value type,
or a key of the other node variety). `la-arch-diagrams` SHALL report malformed metadata syntax as a model parse
finding and refuse to regenerate, and SHALL otherwise ignore metadata. A malformed metadata block SHALL NOT
produce any other model parse finding, and the elements around it SHALL keep their nesting.

#### Scenario: Precise node without package
- **WHEN** a precise top-level element has no `metadata` block, or one without `package`
- **THEN** `la-arch-check` exits 2 with an error naming the element and `package`

#### Scenario: Unknown metadata key
- **WHEN** a node's metadata contains `pakage 'pkg.api'`
- **THEN** `la-arch-check` exits 2 with an error naming the element and `pakage`

#### Scenario: Wrong value type
- **WHEN** a node's metadata sets `claims 'pkg.util'` (a string instead of an array)
- **THEN** `la-arch-check` exits 2 with an error naming the element and `claims`

#### Scenario: Key of the other variety
- **WHEN** a precise node sets `packages`, or a virtual node sets `package` or `claims`
- **THEN** `la-arch-check` exits 2 with an error naming the element and the key

#### Scenario: Metadata on a nested element
- **WHEN** an element nested under a node carries a `metadata` block
- **THEN** `la-arch-check` exits 2 with an error naming the nested element

#### Scenario: Repeated key or second block
- **WHEN** a node's metadata repeats a key, or the node has a second `metadata` block
- **THEN** `la-arch-check` exits 2 with an error naming the element

#### Scenario: Malformed metadata syntax
- **WHEN** a metadata line is outside the subset (for example a double-quoted value, or an unclosed array)
- **THEN** `la-arch-check` exits 2 with an error naming the element, and `la-arch-diagrams` reports a malformed-metadata parse finding, refuses to regenerate and reports no other parse finding for that block

### Requirement: index.yaml carries only repo-wide settings
`architecture/index.yaml` SHALL NOT declare nodes. Its keys SHALL be `root_package`, `source_root`,
`cross_cutting_arc42`, `cross_cutting_specs`, `legacy_arrows`, `diagrams` and `view_depth`. An `index.yaml`
carrying `nodes` SHALL be a setup error naming the key.

#### Scenario: Legacy nodes block rejected
- **WHEN** `index.yaml` still contains a `nodes:` block
- **THEN** `la-arch-check` exits 2 with an error naming `nodes`

### Requirement: Model identity holds by construction
The arch-check SHALL NOT report model-identity findings, and `model-identity` SHALL NOT be a check id an arc42
`[enforced: arch_check:<id>]` tag may name: node ids, nesting and kinds come only from the model.

#### Scenario: Enforced tag naming model-identity
- **WHEN** an arc42 principle carries `[enforced: arch_check:model-identity]`
- **THEN** `la-arch-check` reports `enforced-tags.unknown-id` for it
