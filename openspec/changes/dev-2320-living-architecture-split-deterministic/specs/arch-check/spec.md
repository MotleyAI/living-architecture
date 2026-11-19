## MODIFIED Requirements

### Requirement: Source root is separate from the repo root
Each language section of `architecture/index.yaml` MAY set `source_root`. This is a relative path from the repo
root to the directory that contains that section's roots (`root_package` or `root_packages`); when absent it
defaults to the repo root. A `python` section MAY instead set `source_roots` (see "Python roots may sit under
several source roots"); a section SHALL NOT set both. All source discovery for a language SHALL resolve under its
source root or roots: claims, model-derived child units, top-level units and import-edge measurement. Architecture
files, arc42 docs and OpenSpec specs SHALL resolve from the repo root. Module ids, and therefore findings, SHALL NOT
include a source-root prefix.

#### Scenario: Absent source_root behaves as before
- **WHEN** a language section without `source_root` is checked
- **THEN** sources resolve from the repo root, and every finding equals the pre-change golden apart from fully qualified element ids

#### Scenario: src layout is checked
- **WHEN** the `python` section sets `source_root: python/src` and `root_package: pkg`, and the package lives at `python/src/pkg`
- **THEN** claims, top-level units and measured import edges are resolved under `python/src/pkg`, and findings name modules as `pkg.<...>` without the prefix

#### Scenario: Architecture files stay at the repo root
- **WHEN** a language section sets `source_root: python/src`
- **THEN** `architecture/`, the arc42 files and `openspec/specs/` are still read from the repo root

#### Scenario: Invalid source_root
- **WHEN** a section's `source_root` is absolute, contains `..`, resolves (including via symlinks) outside the repo, is not a directory, or does not contain a configured root
- **THEN** `la-arch-check` exits 2 with an error naming `source_root`

#### Scenario: Invalid root_package
- **WHEN** a section's `root_package` is absolute, has an empty, `.` or `..` segment (e.g. `pkg/`, `.`, `./pkg`), resolves (including via symlinks) outside `source_root`, or is not a directory
- **THEN** `la-arch-check` exits 2 with an error naming `root_package`

#### Scenario: Both source-root forms refused
- **WHEN** a `python` section sets both `source_root` and `source_roots`
- **THEN** `la-arch-check` exits 2 with an error naming both keys

### Requirement: index.yaml carries only repo-wide settings
`architecture/index.yaml` SHALL NOT declare nodes. Its keys SHALL be one section per declared language, keyed by
a language id of the shared languages registry (`python`, `typescript`), plus `cross_cutting_arc42`,
`cross_cutting_specs`, `legacy_arrows`, `diagrams` and `view_depth`, plus any number of repo-owned keys starting
with `x-`, which the tools SHALL ignore. A language section SHALL hold exactly one of `root_package` and
`root_packages` and MAY hold `source_root`; the `python` section MAY hold `source_roots` instead of `source_root`;
the `typescript` section MAY also hold `tsconfig`. At least one language section SHALL be present; `x-` keys do not
count. An `index.yaml` carrying `nodes`, a top-level `root_package`, `source_root` or `source_roots`, a
`typescript` section's `source_roots`, or any other unknown key SHALL be a setup error naming the key.

#### Scenario: Legacy nodes block rejected
- **WHEN** `index.yaml` still contains a `nodes:` block
- **THEN** `la-arch-check` exits 2 with an error naming `nodes`

#### Scenario: Legacy top-level root_package rejected
- **WHEN** `index.yaml` sets `root_package: pkg` at the top level
- **THEN** `la-arch-check` exits 2 with an error naming `root_package`

#### Scenario: Repo-owned key accepted
- **WHEN** `index.yaml` sets `x-guards: {baseline: 0}` next to a valid `python` section
- **THEN** no finding or error concerns `x-guards`

#### Scenario: Unknown key rejected
- **WHEN** `index.yaml` sets `guards: {baseline: 0}`
- **THEN** `la-arch-check` exits 2 with an error naming `guards`

#### Scenario: No language section
- **WHEN** `index.yaml` holds only `x-` keys and repo-wide settings
- **THEN** `la-arch-check` exits 2 with an error saying a language section is required

#### Scenario: TypeScript source_roots rejected
- **WHEN** the `typescript` section sets `source_roots: [a, b]`
- **THEN** `la-arch-check` exits 2 with an error naming `source_roots`

### Requirement: Configured roots are contained and disjoint
Each `root_packages` path SHALL resolve to a directory beneath its section's source root (`source_root`, defaulting
to the repo root, or the one entry of `source_roots` that holds it), including after symlink resolution; with
`source_root`, all roots of a section SHALL share it. Paths SHALL be pairwise disjoint; equal (including a repeated
entry) or nested roots SHALL be rejected. Invalid paths and overlap SHALL produce a setup error naming the affected
`root_packages` entries.

#### Scenario: Invalid roots are rejected
- **WHEN** `root_packages` is not a non-empty list of non-empty strings, or any configured root is absolute, contains a parent segment, is non-canonical, escapes by symlink, or is not a directory
- **THEN** `la-arch-check` exits 2 with a finding naming `root_packages`

#### Scenario: Overlapping roots are rejected
- **WHEN** two configured roots are equal (including a repeated entry) or one is nested under the other
- **THEN** `la-arch-check` exits 2 with a finding naming both conflicting `root_packages`

### Requirement: Facts cover the configured source union
Source discovery, top-level units, claims and runtime import measurement SHALL cover the union of configured roots.
Unit identifiers SHALL remain relative to the source root that holds them, with no configured-root rewriting, so a
Python unit id is its dotted module name. Architecture files and OpenSpec specs SHALL remain relative to the
repository root. Python and TypeScript twins SHALL produce equivalent facts for equivalent layouts.

#### Scenario: Combined facts retain source-root-relative IDs
- **WHEN** a language section configures multiple roots below `source_root`
- **THEN** facts include all roots' units and import edges using IDs relative to `source_root`, and architecture documentation remains repo-root-relative

#### Scenario: Facts across several source roots
- **WHEN** a `python` section sets `source_roots: [a/src, b/src]` and `root_packages: [pa, pb]`, and `pa.x` imports `pb.y` at runtime
- **THEN** the facts hold the units `pa`, `pb` and their children by dotted module name and the edge from `pa.x` to `pb.y`

### Requirement: Nodes declare their mapping in model metadata
A node SHALL be a direct child of a language root element (see "Each declared language has one root element");
it is virtual iff its element kind is declared `#virtual`, and it belongs to its root's language. Every element, a
language root, a node or an element nested at any depth, MAY carry one `metadata { }` block in its element body. A
precise node SHALL set `package` and MAY set `claims`; a virtual node MAY set `packages`; any element MAY set `specs`.
Units SHALL be written in the notation of the node's language: dotted for Python, `/`-separated and extensionless for
TypeScript. Metadata keys and types SHALL be exactly those of the shared node schema for the element's variety
(precise node, virtual node, or any other element), with no other key allowed. Metadata values SHALL use the subset
`key 'value'` or `key ['a', 'b']`: single-quoted strings without escapes, arrays that MAY span lines, no trailing
comma. claims-exist, claims-exactly-once, arc42-exists, spec-mapping and model-truth SHALL take element ids, units
and spec groups only from the model, and `cross_cutting_specs.touches` SHALL resolve against fully qualified model
element ids at any depth.

Every top-level unit of a language (each immediate child unit of a configured root) SHALL be claimed by exactly
one node. A node claims each unit its `package`, `claims` or `packages` names, and a precise node whose `package` is
itself a configured root claims every top-level unit under that root. A top-level unit no node claims SHALL yield
`claims-exactly-once.unclaimed`, and one that two nodes claim SHALL yield `claims-exactly-once.claimed-twice` naming
both.

#### Scenario: Node mapping read from metadata
- **WHEN** the model declares `python = system 'App' { api = node 'API' { metadata { package 'pkg.api'  specs ['api'] } } }` and `pkg.api` exists
- **THEN** `pkg.api` is claimed by `python.api`, spec group `api` is mapped to `python.api`, and no finding concerns either

#### Scenario: Virtual node maps buckets
- **WHEN** a child of the `python` root of a `#virtual` kind sets `packages ['pkg.old']`
- **THEN** `pkg.old` is claimed by that node and its modules attribute to it

#### Scenario: TypeScript node in path notation
- **WHEN** the `typescript` root contains `daemon = node 'Daemon' { metadata { package 'src/daemon' } }` and `src/daemon/` holds a visible source file
- **THEN** `src/daemon` is claimed by `typescript.daemon` and its modules attribute to it

#### Scenario: Multi-line array
- **WHEN** a node sets `claims` with its array split across several lines
- **THEN** the claims are read exactly as the one-line form would be

#### Scenario: No model files
- **WHEN** `architecture/` holds no `model.c4` and no other LikeC4 source file
- **THEN** `la-arch-check` exits 2 with the layout message naming `architecture/model.c4` as missing

#### Scenario: Model without roots
- **WHEN** `architecture/model.c4` holds an empty `specification { }` and an empty `model { }` block
- **THEN** `la-arch-check` exits 2 naming the first declared language whose root element is missing

#### Scenario: Root-package node claims the root's top-level units
- **WHEN** `index.yaml` sets `python: {root_package: pkg}` and the model declares `app = node 'App' { metadata { package 'pkg' } api = node 'API' }`, with `pkg.api` and `pkg.core` on disk
- **THEN** `pkg.api` and `pkg.core` are claimed by `python.app`, modules under `pkg.api` attribute to `python.app.api`, and no claims finding is reported

#### Scenario: Top-level unit claimed through a root and by another node
- **WHEN** node `python.app` has the root `pkg` as its package and node `python.core` has package `pkg.core`
- **THEN** `claims-exactly-once.claimed-twice` is reported for `pkg.core`, naming both nodes, and the exit code is 1

#### Scenario: TypeScript nodes on root packages
- **WHEN** the `typescript` section sets `source_root: node` and `root_packages: [dr/src, la/src]`, and nodes `dr` (package `dr/src`) and `la` (package `la/src`) are declared
- **THEN** every top-level unit under each root is claimed by its node

## ADDED Requirements

### Requirement: Python roots may sit under several source roots
A `python` section MAY set `source_roots` instead of `source_root`: a non-empty list of unique, canonical,
repo-relative directory paths, each resolving (including via symlinks) to a directory inside the repo, none equal
to or nested in another. Each `root_packages` entry (or the `root_package`) SHALL resolve to a directory under
exactly one of them; that source root is its import root. Every `source_roots` problem SHALL be a setup error,
reported with a shared finding before schema validation so both twins print the same text, naming `source_roots`
and the offending entries: a malformed list, an invalid or overlapping entry, a root package found under no entry,
a root package found under more than one entry, and an entry that holds no configured root package.

#### Scenario: Workspace layout checked
- **WHEN** the `python` section sets `source_roots: [python/dr/src, python/la/src]` and `root_packages: [deterministic_refactor, living_architecture]`, each package under its own entry
- **THEN** `la-arch-check` measures both packages, and the model names their units `deterministic_refactor.<...>` and `living_architecture.<...>`

#### Scenario: Root package under no source root
- **WHEN** a `root_packages` entry exists under none of the `source_roots`
- **THEN** `la-arch-check` exits 2 with a finding naming `source_roots` and the entry

#### Scenario: Root package under two source roots
- **WHEN** a directory named by a `root_packages` entry exists under two `source_roots` entries
- **THEN** `la-arch-check` exits 2 with a finding naming the entry and both source roots

#### Scenario: Unused source root
- **WHEN** a `source_roots` entry holds no configured root package
- **THEN** `la-arch-check` exits 2 with a finding naming that entry

#### Scenario: Invalid or overlapping source roots
- **WHEN** `source_roots` is empty, not a list of strings, repeats an entry, holds an absolute, non-canonical or escaping path, a path that is not a directory, or two entries one inside the other
- **THEN** `la-arch-check` exits 2 with a finding naming `source_roots`

#### Scenario: Same result from either twin
- **WHEN** a repo with `source_roots` is checked through the PyPI twin and through the npm twin
- **THEN** stdout, stderr and the exit code are byte-identical
