## MODIFIED Requirements

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
- **WHEN** the `typescript` section sets `source_root: node` and `root_packages: [trmv/src, la/src]`, and nodes `trmv` (package `trmv/src`) and `la` (package `la/src`) are declared
- **THEN** every top-level unit under each root is claimed by its node

### Requirement: Python roots may sit under several source roots
A `python` section MAY set `source_roots` instead of `source_root`: a non-empty list of unique, canonical,
repo-relative directory paths, each resolving (including via symlinks) to a directory inside the repo, none equal
to or nested in another. Each `root_packages` entry (or the `root_package`) SHALL resolve to a directory under
exactly one of them; that source root is its import root. Every `source_roots` problem SHALL be a setup error,
reported with a shared finding before schema validation so both twins print the same text, naming `source_roots`
and the offending entries: a malformed list, an invalid or overlapping entry, a root package found under no entry,
a root package found under more than one entry, and an entry that holds no configured root package.

#### Scenario: Workspace layout checked
- **WHEN** the `python` section sets `source_roots: [python/trmv/src, python/la/src]` and `root_packages: [trmv, living_architecture]`, each package under its own entry
- **THEN** `la-arch-check` measures both packages, and the model names their units `trmv.<...>` and `living_architecture.<...>`

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
