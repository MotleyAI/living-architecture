## ADDED Requirements

### Requirement: Any element owns spec groups
A spec group SHALL be mapped by the `specs` metadata of any model element (a language root, a node, or an element
nested at any depth) or by `cross_cutting_specs`. Ownership SHALL be read over the model elements in declaration
order, then over `cross_cutting_specs` in file order; a group mapped a second time SHALL yield
`spec-mapping.mapped-twice` naming the first and the second owner. Each `touches` entry SHALL name a fully qualified
model element at any depth, a language root included; an entry naming no model element SHALL yield
`spec-mapping.unknown-element` (`spec-mapping: {group} touches unknown element {element}`).

#### Scenario: Nested element in touches
- **WHEN** `cross_cutting_specs` maps `usage` with `touches: [typescript.domain.usage]` and the model nests `usage` under `typescript.domain`
- **THEN** no spec-mapping finding concerns the entry

#### Scenario: Root in touches
- **WHEN** `cross_cutting_specs` maps `contract` with `touches: [python]` and `python` is a language root
- **THEN** no spec-mapping finding concerns the entry

#### Scenario: Nested element owns a spec group
- **WHEN** the element `python.api.handlers` carries `metadata { specs ['handlers'] }` and `openspec/specs/handlers/spec.md` exists
- **THEN** `handlers` is mapped to `python.api.handlers` and no spec-mapping finding concerns it

#### Scenario: Root owns a spec group
- **WHEN** the `python` root carries `metadata { specs ['twin'] }` and `openspec/specs/twin/spec.md` exists
- **THEN** `twin` is mapped to `python` and no spec-mapping finding concerns it

#### Scenario: Unknown touched element
- **WHEN** `cross_cutting_specs` maps `usage` with `touches: [python.api.nothing]` and no such element exists
- **THEN** `spec-mapping: usage touches unknown element python.api.nothing` is reported

#### Scenario: Group owned by a node and by its nested element
- **WHEN** `python.api` and `python.api.handlers` both list `api` in `specs`
- **THEN** `spec-mapping: api mapped by both python.api and python.api.handlers` is reported

#### Scenario: Group owned by an element and cross-cutting
- **WHEN** `python.api.handlers` lists `api` in `specs` and `cross_cutting_specs` also maps `api`
- **THEN** `spec-mapping: api mapped by both python.api.handlers and cross_cutting_specs` is reported

### Requirement: arc42 docs are named by element id and sit directly in architecture/
`architecture/system.arc42.md` SHALL exist, else `arc42-exists.system-missing`. An element MAY have an arc42 doc; when
it does, the doc SHALL be `architecture/<element id>.arc42.md`, named by the element's fully qualified id, a language
root included. Every `cross_cutting_arc42` entry SHALL be `architecture/<name>.arc42.md` with no `/` in `<name>`
(else `arc42-exists.cross-cutting-not-flat`), SHALL exist (else `arc42-exists.cross-cutting-missing`), and SHALL NOT
be the doc of a model element (else `arc42-exists.cross-cutting-is-element`). Each `*.arc42.md` in a subdirectory of
`architecture/`, at any depth, SHALL yield `arc42-exists.nested-doc` (`arc42-exists: {doc} must sit directly in
architecture/`); the walk SHALL follow the layout check's rules: a symlink to a file counts as a file, a symlinked
directory is not descended into. Each `architecture/*.arc42.md` that is neither `architecture/system.arc42.md`, nor the
doc of a model element, nor a `cross_cutting_arc42` entry SHALL yield `arc42-exists.orphan`. arc42-exists findings
SHALL be printed in this order: system-missing; per `cross_cutting_arc42` entry in file order, not-flat, missing,
is-element; nested docs; orphans; paths in code-point order within each kind. enforced-tags SHALL check every
`architecture/*.arc42.md`.

#### Scenario: Nested element doc recognised
- **WHEN** the model nests `handlers` under `python.api` and `architecture/python.api.handlers.arc42.md` exists
- **THEN** no arc42-exists finding concerns that doc, and enforced-tags checks it

#### Scenario: Root doc recognised
- **WHEN** `architecture/python.arc42.md` exists beside `architecture/system.arc42.md`
- **THEN** no arc42-exists finding concerns either doc

#### Scenario: Element without a doc
- **WHEN** no `architecture/python.api.arc42.md` exists for the element `python.api`
- **THEN** no arc42-exists finding concerns `python.api`

#### Scenario: Doc of a renamed element is orphaned
- **WHEN** `architecture/python.store.arc42.md` exists, the model has no element `python.store`, and no `cross_cutting_arc42` entry names it
- **THEN** `arc42-exists: architecture/python.store.arc42.md is orphaned — not architecture/system.arc42.md, the doc of a model element, or in cross_cutting_arc42` is reported

#### Scenario: Doc in a subfolder
- **WHEN** `architecture/python/api.arc42.md` exists
- **THEN** `arc42-exists: architecture/python/api.arc42.md must sit directly in architecture/` is reported

#### Scenario: Symlinked directory not descended
- **WHEN** `architecture/link` is a symlink to a directory holding `x.arc42.md`
- **THEN** no arc42-exists finding concerns `architecture/link/x.arc42.md`

#### Scenario: Cross-cutting doc outside architecture/
- **WHEN** `cross_cutting_arc42` lists `docs/security.arc42.md`
- **THEN** `arc42-exists.cross-cutting-not-flat` is reported for `docs/security.arc42.md`

#### Scenario: Cross-cutting entry naming an element doc
- **WHEN** `cross_cutting_arc42` lists `architecture/python.api.arc42.md` and `python.api` is a model element
- **THEN** `arc42-exists.cross-cutting-is-element` is reported naming the doc and `python.api`

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

### Requirement: Nested elements map to units by convention
An element nested under a precise node, at any depth, SHALL map to the unit formed by appending its path below
the node to the node's `package` in the node's language notation (`python.api.a.b` → `<package>.a.b`;
`typescript.api.a.b` → `<package>/a/b`) and SHALL carry no mapping keys. Each such unit that does not exist under
its language's `source_root` SHALL yield `claims-exist.child-missing`. Each such unit that equals, contains or
nests in a unit declared in any node's metadata of the same language other than its own node's `package` SHALL
yield one `claims-exactly-once.child-collides`, naming the first such unit in sorted order. A virtual node
containing any element SHALL yield one `claims-exist.virtual-children`, and elements under a virtual node SHALL
map to no unit. Modules SHALL attribute to the finest mapped element of their language, and the import law SHALL
apply between mapped elements at every depth.

#### Scenario: Model child governed with no index entry
- **WHEN** the model nests `handlers` under `python.api` (package `pkg.api`), `pkg.api.handlers` exists, and `index.yaml` mentions neither
- **THEN** modules under `pkg.api.handlers` attribute to `python.api.handlers`, an arrow `api.handlers -> core` inside the root covering a measured edge is live, and an unmodelled import from `pkg.api.handlers` to `pkg.store` is reported as `model-truth.missing-edge` from `python.api.handlers`

#### Scenario: Grandchild governed
- **WHEN** the model nests `x` under `python.api.handlers` and `pkg.api.handlers.x` exists
- **THEN** modules under `pkg.api.handlers.x` attribute to `python.api.handlers.x`, and no claims finding concerns it

#### Scenario: Model child missing on disk
- **WHEN** the model nests `inner` under `python.core` (package `pkg.core`) and `pkg.core.inner` does not exist
- **THEN** `la-arch-check` reports `claims-exist: element python.core.inner maps to pkg.core.inner, which does not exist on disk` and exits 1

#### Scenario: Grandchild missing on disk
- **WHEN** the model nests `y` under `python.api.handlers` and `pkg.api.handlers.y` does not exist
- **THEN** `claims-exist.child-missing` is reported for `python.api.handlers.y`

#### Scenario: TypeScript child missing on disk
- **WHEN** the model nests `pty` under `typescript.daemon` (package `src/daemon`) and neither `src/daemon/pty/` with a visible source file nor one `src/daemon/pty.<ext>` module exists
- **THEN** `claims-exist.child-missing` is reported for `typescript.daemon.pty` naming `src/daemon/pty`

#### Scenario: Child collides with another node's claim
- **WHEN** node `python.core` claims `pkg.api.handlers` and the model nests `handlers` under `python.api` (package `pkg.api`)
- **THEN** `claims-exactly-once: element python.api.handlers (pkg.api.handlers) collides with declared unit pkg.api.handlers` is reported

#### Scenario: Descendants of one node do not collide with each other
- **WHEN** the model nests `x` under `python.api.handlers` and both units exist
- **THEN** no `child-collides` finding is reported

#### Scenario: Virtual node contains elements
- **WHEN** a virtual node contains one or more nested elements
- **THEN** exactly one `claims-exist: virtual node <node> may not contain elements` is reported, and its nested elements map to no unit

#### Scenario: Virtual-kind element nested under a precise node
- **WHEN** an element of a `#virtual` kind is nested under a precise node
- **THEN** it maps by convention like any other nested element

#### Scenario: Element under a virtual node owns specs
- **WHEN** an element nested under a virtual node carries `metadata { specs ['old'] }`
- **THEN** `old` is mapped to that element, and `claims-exist.virtual-children` is still reported for the node

### Requirement: Malformed node metadata is a setup error
`la-arch-check` SHALL exit 2 with a setup error naming the element when element metadata is malformed: a line
outside the metadata subset, a repeated key, a second `metadata` block, metadata that violates the shared node schema
for the element's variety (a missing required key, an unknown key, a wrong value type, or a key of another variety,
such as a mapping key on a root or a nested element), or the retired `arc42` key on any element
(`arch-check.arc42-key-retired`: `model element {element}: the arc42 key is retired; its doc is
architecture/{element}.arc42.md — run la-arch-migrate`). For each element, syntax problems SHALL be reported alone;
otherwise the retired-key error SHALL come first, followed by the schema errors of its other keys; elements SHALL be
reported in model order. `la-arch-diagrams` SHALL report malformed metadata syntax as a model parse finding and refuse
to regenerate, and SHALL otherwise ignore metadata. A malformed metadata block SHALL NOT produce any other model parse
finding, and the elements around it SHALL keep their nesting.

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
- **WHEN** an element nested under a node sets `package 'pkg.api.x'`
- **THEN** `la-arch-check` exits 2 with an error naming the nested element and `package`

#### Scenario: Empty metadata on a nested element
- **WHEN** an element nested under a node carries an empty `metadata { }` block
- **THEN** no setup error or finding concerns it

#### Scenario: Retired arc42 key
- **WHEN** the node `python.api` sets `arc42 'architecture/api.arc42.md'`
- **THEN** `la-arch-check` exits 2 with `model element python.api: the arc42 key is retired; its doc is architecture/python.api.arc42.md — run la-arch-migrate`

#### Scenario: Retired key beside an invalid key
- **WHEN** a nested element sets both `arc42 'architecture/x.arc42.md'` and `claims ['pkg.x']`
- **THEN** `la-arch-check` exits 2 with the retired-key error for that element followed by the schema error naming `claims`

#### Scenario: Repeated key or second block
- **WHEN** a node's metadata repeats a key, or the node has a second `metadata` block
- **THEN** `la-arch-check` exits 2 with an error naming the element

#### Scenario: Malformed metadata syntax
- **WHEN** a metadata line is outside the subset (for example a double-quoted value, or an unclosed array)
- **THEN** `la-arch-check` exits 2 with an error naming the element, and `la-arch-diagrams` reports a malformed-metadata parse finding, refuses to regenerate and reports no other parse finding for that block

### Requirement: Each declared language has one root element
For each language section of `index.yaml` the model SHALL have exactly one top-level element whose id equals the
language id, of any element kind; it is that language's root, and its unit is the section's `root_package`. A
root SHALL carry no mapping keys and MAY carry `specs`. A top-level element whose id is not a declared language, a
declared language with no root element, and a mapping key on a root SHALL each be a setup error (exit 2) naming the
element or language.

#### Scenario: Single-language model
- **WHEN** `index.yaml` declares only `python` and the model wraps every node in `python = system 'App' { ... }`
- **THEN** the nodes are checked against the `python` section's `root_package`

#### Scenario: Undeclared top-level element
- **WHEN** the model has a top-level element `core` and `index.yaml` declares only `python`
- **THEN** `la-arch-check` exits 2 with an error naming `core`

#### Scenario: Declared language without a root
- **WHEN** `index.yaml` declares `typescript` and the model has no top-level `typescript` element
- **THEN** `la-arch-check` exits 2 with an error naming `typescript`

#### Scenario: Metadata on a root
- **WHEN** the `python` root element sets `package 'pkg'`
- **THEN** `la-arch-check` exits 2 with an error naming `python` and `package`

#### Scenario: Specs on a root
- **WHEN** the `python` root element carries `metadata { specs ['twin'] }`
- **THEN** no setup error concerns it

### Requirement: Views are scoped to a language root
Every view SHALL be declared `view <id> of <root> { ... }` with a declared language root. Every element name in a
view body (`include X`, `X -> *`, `* -> X`) SHALL name an element at any depth under that root, written relative to
the root; a name that does not, a fully qualified one included, SHALL be an unknown-id views parse finding. Every
accepted name SHALL resolve to the element LikeC4 resolves it to. With the root's children at level 1, a selection X
(an included element or a predicate anchor) SHALL reach down to level `level(X) + view_depth - 1`. `include X` SHALL
show X and its descendants down to X's reach, and `include *` SHALL include every child of the root. `X -> *`
(`* -> X`) SHALL match each relation whose source (target) is X or a descendant of X, and SHALL show both endpoints of
a matched relation, each cut to its ancestor at X's reach, with their ancestors. An element SHALL be shown when any
selection shows it. A relation SHALL be drawn when each endpoint is in the subtree of an included element, or when it
matches a predicate; it SHALL be drawn between the nearest shown ancestor-or-self of each endpoint, and not at all
when either has none or both coincide. The generated mermaid SHALL never draw the root: element ids, levels,
`view_depth`, predicate anchors and edges SHALL be computed with the root prefix stripped, so a model wrapped in a root
renders byte-identically to the same model without it. A view without `of`, or with `of` naming anything but a
declared root, SHALL be a views parse finding.

#### Scenario: Wrapped model renders identically
- **WHEN** a single-language repo's model, views and index are migrated (model wrapped in `python`, views given `of python`, `root_package` moved into the section) and `la-arch-diagrams` runs
- **THEN** every generated diagram, including nested elements, `->` predicates, legacy edges and custom `view_depth`, is byte-identical to the pre-migration output

#### Scenario: Top-level selections unchanged
- **WHEN** a view includes and anchors only children of its root
- **THEN** its generated diagram is byte-identical to the output before nested selections were allowed

#### Scenario: Nested include reaches relative to itself
- **WHEN** the root holds `api { handlers { x { y } } }`, `view_depth` is 2, and the view is `include api.handlers`
- **THEN** the diagram shows `api.handlers` and `api.handlers.x`, and neither `api` nor `api.handlers.x.y`

#### Scenario: Overlapping includes
- **WHEN** the root holds `api { handlers { x } other { z } }`, `view_depth` is 2, and the view is `include api, api.handlers`
- **THEN** the diagram shows `api`, `api.handlers`, `api.other` and `api.handlers.x`, and not `api.other.z`

#### Scenario: Nested predicate anchor
- **WHEN** the root holds `api { handlers { x } }` and `core { store { sql } }` with `api.handlers.x -> core.store.sql`, `view_depth` is 2, and the view is `include api.handlers -> *`
- **THEN** the diagram shows `api.handlers.x` and `core.store.sql` with their ancestors and one edge between them

#### Scenario: Anchor matches its own endpoint
- **WHEN** the root holds `api.handlers -> core` and the view is `include * -> core`
- **THEN** the relation is matched and drawn

#### Scenario: Fully qualified name rejected
- **WHEN** a view `of python` includes `python.api`
- **THEN** a views parse finding names `python.api` as unknown

#### Scenario: Unscoped view
- **WHEN** `views.c4` declares `view landscape { include * }`
- **THEN** a views parse finding names `landscape`, and `la-arch-diagrams` refuses to regenerate

#### Scenario: View scoped to a non-root
- **WHEN** a view is declared `of python.core`
- **THEN** a views parse finding names the view

### Requirement: Element ids are fully qualified
Every element id the arch-check prints or reads SHALL be the fully qualified model id including the language root:
in every finding naming a node, element or relation endpoint, in arc42 doc names, and in
`cross_cutting_specs.touches`. Module ids in findings SHALL stay language-native (`pkg.api.x`, `src/api/x`).

#### Scenario: Missing edge names qualified elements
- **WHEN** a measured Python edge from `pkg.engine.a` to `pkg.memories.b` has no covering arrow
- **THEN** the finding reads `model-truth: measured runtime edge python.engine -> python.memories is missing from the model (import pkg.engine.a -> pkg.memories.b)`

#### Scenario: Unqualified touches
- **WHEN** `cross_cutting_specs` lists `touches: [core]` and the node is `python.core`
- **THEN** `spec-mapping.unknown-element` names `core`

### Requirement: Spec groups in live changes count as present
A spec group SHALL be present when a directory of that name exists directly under `openspec/specs/` or directly
under `openspec/changes/<id>/specs/` for any change directory `<id>` other than `archive`. A change under
`openspec/changes/archive/` SHALL NOT make a group present. The spec-mapping check SHALL use this one set of
present groups: a present group mapped by no element and not cross-cutting SHALL yield `spec-mapping.unmapped`
(`spec group {group} is mapped by no element and not cross-cutting`); a mapped group that is not present SHALL yield
`spec-mapping.dir-missing` (`{group} is mapped but has no spec dir in openspec/specs or a live change`); a mapped,
present group none of whose directories contains a `spec.md` at any depth SHALL yield `spec-mapping.no-spec-md`
(`spec group {group} contains no spec.md`).

#### Scenario: New capability mapped during its change
- **WHEN** group `logging` is mapped, `openspec/specs/logging/` does not exist, and `openspec/changes/add-logging/specs/logging/spec.md` exists
- **THEN** no spec-mapping finding is reported

#### Scenario: Capability present only in an archived change
- **WHEN** group `logging` is mapped, `openspec/specs/logging/` does not exist, and only `openspec/changes/archive/2026-01-01-add-logging/specs/logging/spec.md` exists
- **THEN** `spec-mapping.dir-missing` is reported for `logging`

#### Scenario: Unmapped capability in a live change
- **WHEN** `openspec/changes/add-metrics/specs/metrics/spec.md` exists and no element or `cross_cutting_specs` entry maps `metrics`
- **THEN** `spec-mapping.unmapped` is reported for `metrics`

#### Scenario: spec.md only in the live change
- **WHEN** group `logging` is mapped, `openspec/specs/logging/` holds no `spec.md`, and `openspec/changes/add-logging/specs/logging/spec.md` exists
- **THEN** no spec-mapping finding is reported

#### Scenario: Live-change group without spec.md
- **WHEN** group `logging` is mapped, `openspec/specs/logging/` does not exist, and `openspec/changes/add-logging/specs/logging/` exists with no `spec.md` at any depth
- **THEN** `spec-mapping.no-spec-md` is reported for `logging`
