## MODIFIED Requirements

### Requirement: Nodes declare their mapping in model metadata
A node SHALL be a direct child of a language root element (see "Each declared language has one root element");
it is virtual iff its element kind is declared `#virtual`, and it belongs to its root's language. A node SHALL
declare its code mapping and pointers in one `metadata { }` block in its element body: a precise node SHALL set
`package` and MAY set `claims`; a virtual node MAY set `packages`; either MAY set `arc42` (a string) and `specs`.
Units SHALL be written in the notation of the node's language: dotted for Python, `/`-separated and
extensionless for TypeScript. Metadata keys and types SHALL be exactly those of the shared node schema, with no
other key allowed. Metadata values SHALL use the subset `key 'value'` or `key ['a', 'b']`: single-quoted strings
without escapes, arrays that MAY span lines, no trailing comma. claims-exist, claims-exactly-once, arc42-exists,
spec-mapping and model-truth SHALL take node ids, units, docs and spec groups only from the model, and
`cross_cutting_specs.touches` SHALL resolve against fully qualified model node ids.

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
