# arch-check Specification

## Purpose
The architecture cross-check: code, the LikeC4 model, arc42 docs and OpenSpec specs agree, and the model is the
repo's single import law. This delta covers where source code is located relative to the repo root.

## Requirements

### Requirement: Source root is separate from the repo root
Each language section of `architecture/index.yaml` MAY set `source_root`. This is a relative path from the repo
root to the directory that contains that section's `root_package`; when absent it defaults to the repo root. All
source discovery for a language SHALL resolve under its `source_root`: claims, model-derived child units,
top-level units and import-edge measurement. Architecture files, arc42 docs and OpenSpec specs SHALL resolve from
the repo root. Module ids, and therefore findings, SHALL NOT include the `source_root` prefix.

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
- **WHEN** a section's `source_root` is absolute, contains `..`, resolves (including via symlinks) outside the repo, is not a directory, or does not contain `root_package`
- **THEN** `la-arch-check` exits 2 with an error naming `source_root`

#### Scenario: Invalid root_package
- **WHEN** a section's `root_package` is absolute, has an empty, `.` or `..` segment (e.g. `pkg/`, `.`, `./pkg`), resolves (including via symlinks) outside `source_root`, or is not a directory
- **THEN** `la-arch-check` exits 2 with an error naming `root_package`

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
- **WHEN** `architecture/model/` has no `.c4` file
- **THEN** `la-arch-check` exits 2 naming the first declared language whose root element is missing

### Requirement: Nested elements map to units by convention
An element nested under a precise node, at any depth, SHALL map to the unit formed by appending its path below
the node to the node's `package` in the node's language notation (`python.api.a.b` → `<package>.a.b`;
`typescript.api.a.b` → `<package>/a/b`) and SHALL carry no metadata. Each such unit that does not exist under
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
`architecture/index.yaml` SHALL NOT declare nodes. Its keys SHALL be one section per declared language, keyed by
a language id of the shared languages registry (`python`, `typescript`), plus `cross_cutting_arc42`,
`cross_cutting_specs`, `legacy_arrows`, `diagrams` and `view_depth`, plus any number of repo-owned keys starting
with `x-`, which the tools SHALL ignore. A language section SHALL hold `root_package` and MAY hold `source_root`;
the `typescript` section MAY also hold `tsconfig`. At least one language section SHALL be present; `x-` keys do
not count. An `index.yaml` carrying `nodes`, a top-level `root_package` or `source_root`, or any other unknown
key SHALL be a setup error naming the key.

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

### Requirement: Model identity holds by construction
The arch-check SHALL NOT report model-identity findings, and `model-identity` SHALL NOT be a check id an arc42
`[enforced: arch_check:<id>]` tag may name: node ids, nesting and kinds come only from the model.

#### Scenario: Enforced tag naming model-identity
- **WHEN** an arc42 principle carries `[enforced: arch_check:model-identity]`
- **THEN** `la-arch-check` reports `enforced-tags.unknown-id` for it

### Requirement: Each declared language has one root element
For each language section of `index.yaml` the model SHALL have exactly one top-level element whose id equals the
language id, of any element kind; it is that language's root, and its unit is the section's `root_package`. A
root SHALL carry no metadata. A top-level element whose id is not a declared language, a declared language with
no root element, and metadata on a root SHALL each be a setup error (exit 2) naming the element or language.

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
- **WHEN** the `python` root element carries a `metadata` block
- **THEN** `la-arch-check` exits 2 with an error naming `python`

### Requirement: Relations are written inside a language root
A relation SHALL be written in the body of a language root, with each endpoint resolved by prefixing the root id
(`engine -> core` inside `python { }` is `python.engine -> python.core`). An endpoint that does not resolve to an
element under that root SHALL yield `c4.unknown-endpoint` with the resolved id. A relation inside a node body
SHALL yield `c4.relation-in-body`, and a relation outside every root SHALL yield a model parse finding naming it.
A relation between elements under different roots is therefore not expressible.

#### Scenario: Wrapped relations keep their text
- **WHEN** an existing model's relation lines are moved unchanged into the `python` root body
- **THEN** every relation resolves to the same elements, now prefixed `python.`

#### Scenario: Root-prefixed endpoint inside a root
- **WHEN** the `python` root body holds `python.api -> core`
- **THEN** `c4.unknown-endpoint` names `python.python.api`

#### Scenario: Same local ids under two roots
- **WHEN** both roots contain `api` and `core`, and each root body holds `api -> core`
- **THEN** the model has the two relations `python.api -> python.core` and `typescript.api -> typescript.core`

#### Scenario: Relation outside every root
- **WHEN** the model block holds `python.api -> typescript.web` outside both roots
- **THEN** a model parse finding names the relation and no relation is recorded

### Requirement: Views are scoped to a language root
Every view SHALL be declared `view <id> of <root> { ... }` with a declared language root, and its include
names SHALL be relative to that root, the root's children being the top level of the include grammar. The
generated mermaid SHALL never draw the root: element ids, levels, `view_depth`, predicate anchors and edges SHALL
be computed with the root prefix stripped, so a model wrapped in a root renders byte-identically to the same
model without it. A view without `of`, or with `of` naming anything but a declared root, SHALL be a views parse
finding.

#### Scenario: Wrapped model renders identically
- **WHEN** a single-language repo's model, views and index are migrated (model wrapped in `python`, views given `of python`, `root_package` moved into the section) and `la-arch-diagrams` runs
- **THEN** every generated diagram, including nested elements, `->` predicates, legacy edges and custom `view_depth`, is byte-identical to the pre-migration output

#### Scenario: Unscoped view
- **WHEN** `views.c4` declares `view landscape { include * }`
- **THEN** a views parse finding names `landscape`, and `la-arch-diagrams` refuses to regenerate

#### Scenario: View scoped to a non-root
- **WHEN** a view is declared `of python.core`
- **THEN** a views parse finding names the view

### Requirement: Element ids are fully qualified
Every element id the arch-check prints or reads SHALL be the fully qualified model id including the language root:
in every finding naming a node, element or relation endpoint, and in `cross_cutting_specs.touches`. Module ids
in findings SHALL stay language-native (`pkg.api.x`, `src/api/x`).

#### Scenario: Missing edge names qualified elements
- **WHEN** a measured Python edge from `pkg.engine.a` to `pkg.memories.b` has no covering arrow
- **THEN** the finding reads `model-truth: measured runtime edge python.engine -> python.memories is missing from the model (import pkg.engine.a -> pkg.memories.b)`

#### Scenario: Unqualified touches
- **WHEN** `cross_cutting_specs` lists `touches: [core]` and the node is `python.core`
- **THEN** `spec-mapping.unknown-node` names `core`

### Requirement: Principle items may name their language
An arc42 principle item MAY carry one `[lang: <language>]` tag naming a declared language section; an untagged
item binds every language. A tag naming an undeclared language SHALL yield an enforced-tags finding naming the
doc and the language. A second `[lang:]` tag on one item, or a malformed one, SHALL yield
`enforced-tags.malformed`. The tag SHALL NOT replace the item's status tag.

#### Scenario: Declared language tag
- **WHEN** a principle item in a repo declaring `python` and `typescript` carries `[lang: typescript] [review]`
- **THEN** no finding concerns it

#### Scenario: Undeclared language tag
- **WHEN** a principle item carries `[lang: rust]` and `index.yaml` declares only `python`
- **THEN** an enforced-tags finding names the doc and `rust`

### Requirement: TypeScript units
A TypeScript unit SHALL be an extensionless path relative to the section's `source_root`. It SHALL exist iff it
names a directory containing at least one visible source file at any depth, or exactly one visible module file
`<unit>.<ext>` with `<ext>` among `.ts .tsx .mts .cts .js .jsx .mjs .cjs`. A unit naming both such a directory
and a module file, or module files with more than one extension, SHALL be ambiguous and yield a `claims-exist`
ambiguity finding listing the sorted candidate paths (one template for declared units, one for derived elements).
Visible source files SHALL exclude files matching the shared TypeScript test globs, `*.d.ts` files, and anything
under a `node_modules` directory. Symlinks SHALL be followed only while their real path stays under the section's
`source_root`. The top-level units SHALL be every visible source file directly under `root_package` other than the
root barrel `<root_package>/index.<ext>`, and every directory directly under it that contains a visible source
file. A module id SHALL be its extensionless path, with `<dir>/index.<ext>` shown as `<dir>`.

#### Scenario: Directory unit
- **WHEN** a node claims `src/cli` and `src/cli/main.ts` exists
- **THEN** `src/cli` exists and modules under it attribute to the node

#### Scenario: Module-file unit
- **WHEN** a node claims `src/util` and only `src/util.mjs` exists
- **THEN** `src/util` exists

#### Scenario: Ambiguous unit
- **WHEN** a node claims `src/util` and both `src/util.ts` and `src/util/x.ts` exist
- **THEN** a `claims-exist` ambiguity finding lists `src/util/` and `src/util.ts`

#### Scenario: Invisible files
- **WHEN** `src/a/` contains only `x.test.ts`, `y.d.ts` and `node_modules/z.js`
- **THEN** `src/a` is not a top-level unit and a claim of `src/a` is missing

#### Scenario: Root barrel exempt
- **WHEN** `src/index.ts` exists and no node claims `src/index`
- **THEN** no unclaimed finding concerns it

#### Scenario: Directory without sources
- **WHEN** `src/assets/` holds only images
- **THEN** it is not a top-level unit

### Requirement: TypeScript import edges
Import edges SHALL be measured from every visible TypeScript source file with the TypeScript 6.0 compiler API.
These forms SHALL count: static `import`, `export … from`, side-effect `import 'x'`, `import x = require('x')`,
`import('x')` and `require('x')` with a string-literal argument. Calls with non-literal arguments SHALL be
ignored. Type-only forms SHALL be excluded by syntax alone: `import type`, `export type`, `export type * from`,
`import type x = require()`, an import or export with at least one named specifier, every one of them `type`, type-position
`import('x')` (including `typeof import('x')` and import types nested in other types), and `/// <reference>`
directives. An import with at least one value specifier SHALL count even if the value is used only in type
positions.

#### Scenario: Type-only imports produce no edges
- **WHEN** `src/a/x.ts` only has `import type {T} from '../b/y'`, `import {type U} from '../b/y'` and `let v: import('../b/y').V`
- **THEN** no edge from `src/a` to `src/b` is measured

#### Scenario: Mixed specifiers count
- **WHEN** `src/a/x.ts` has `import {type T, f} from '../b/y'`
- **THEN** an edge from `src/a` to `src/b` is measured

#### Scenario: Dynamic and CommonJS forms count
- **WHEN** `src/a/x.ts` has `await import('../b/y')` and `src/c/z.cjs` has `require('../b/y')`
- **THEN** edges from `src/a` and from `src/c` to `src/b` are measured

#### Scenario: Non-literal dynamic import ignored
- **WHEN** `src/a/x.ts` has `import(name)`
- **THEN** no edge is measured from it

### Requirement: TypeScript module resolution
Specifiers SHALL be resolved with the compiler options of the repo's tsconfig: the section's `tsconfig` when set
(repo-relative), else the nearest `tsconfig.json` from `<source_root>/<root_package>` up to the repo root, else
the TypeScript defaults with `moduleResolution: bundler`. Resolution SHALL honour `paths`, `baseUrl`,
`moduleResolution`, `.js` specifiers naming `.ts` sources, directory index files and project references, and
SHALL resolve JavaScript files even when the tsconfig disables `allowJs`. With project references, each file
SHALL resolve with the options of the first project, in depth-first reference order, whose file list contains
it, else the root config's; reference cycles SHALL be tolerated. A resolution to a referenced project's emitted
declaration file SHALL be mapped to the source that emits it. tsconfig files SHALL be read, never executed.
Classification:
- a target whose real path lies under the section's `root_package` is internal and attributes to its element;
- a Node builtin, a target resolved into `node_modules`, and an unresolved bare specifier are external (no edge);
- a target whose real path lies outside `root_package` is unattributed (no edge);
- an unresolved relative specifier is attributed lexically: the importer's directory joined with the specifier,
  normalized, with a trailing `?…`/`#…` suffix and a known source extension stripped, and unattributed if it
  leaves `root_package`.

#### Scenario: paths alias resolves internally
- **WHEN** the tsconfig maps `@app/*` to `src/*` and `src/a/x.ts` imports `@app/b/y`
- **THEN** an edge from `src/a` to `src/b` is measured

#### Scenario: npm and node builtins are external
- **WHEN** `src/a/x.ts` imports `lodash`, `node:fs` and `react/jsx-runtime`
- **THEN** no edge is measured from these imports

#### Scenario: .js specifier names a TS source
- **WHEN** under `moduleResolution: nodenext` `src/a/x.ts` imports `../b/y.js` and only `src/b/y.ts` exists
- **THEN** an edge from `src/a` to `src/b` is measured

#### Scenario: Project reference output maps to source
- **WHEN** a referenced project emits `lib/dist/index.d.ts` from `src/lib/index.ts` and `src/app/x.ts` resolves an import to `lib/dist/index.d.ts`
- **THEN** an edge from `src/app` to `src/lib` is measured

#### Scenario: Unresolved relative import attributed lexically
- **WHEN** `src/a/x.ts` imports `../b/missing` and no such file exists
- **THEN** an edge from `src/a` to `src/b` is measured with witness `src/b/missing`

#### Scenario: Escaping relative import unattributed
- **WHEN** `src/a/x.ts` imports `../../outside/y`
- **THEN** no edge is measured from that import

### Requirement: Mixed-language repos are checked as one
`la-arch-check` SHALL check every declared language. For each language it SHALL obtain that language's facts
(which units exist, are missing or are ambiguous with their candidates, the top-level units, and the measured
element-level edges each with one witness) natively for its own language, or from the other twin (see
twin-forwarding). The claims checks SHALL run per language on those facts; model-truth SHALL run once over the
union of all languages' edges against all arrows. Within a language, edges SHALL be measured over source modules
and targets in sorted module-id order, keeping the first witness per element edge; across languages the witness
SHALL come from the first language in id order. Findings SHALL be printed per-language claims findings in language
id order, then arc42, spec-mapping, baseline-ratchet, model-truth, enforced-tags and diagrams-fresh, so stdout,
stderr and the exit code SHALL be identical whichever twin is invoked.

#### Scenario: Disjoint roots
- **WHEN** a repo declares a `python` root with `api -> core` and a `typescript` root with `web -> shared`, and each edge is measured in its language
- **THEN** no model-truth finding is reported

#### Scenario: Arrow measured only in its own language
- **WHEN** the `typescript` root has `web -> shared` and only Python edges are measured
- **THEN** `model-truth.dead` is reported for `typescript.web -> typescript.shared`

#### Scenario: Identical output from both twins
- **WHEN** the same mixed-language repo is checked through the PyPI twin and through the npm twin
- **THEN** exit code, stdout and stderr are byte-identical

#### Scenario: Single-language order unchanged
- **WHEN** a repo declares only `python`
- **THEN** findings appear in today's order with qualified element ids

### Requirement: Spec groups in live changes count as present
A spec group SHALL be present when a directory of that name exists directly under `openspec/specs/` or directly
under `openspec/changes/<id>/specs/` for any change directory `<id>` other than `archive`. A change under
`openspec/changes/archive/` SHALL NOT make a group present. The spec-mapping check SHALL use this one set of
present groups: a present group mapped by no node and not cross-cutting SHALL yield `spec-mapping.unmapped`
(`spec group {group} is mapped by no node and not cross-cutting`); a mapped group that is not present SHALL yield
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
- **WHEN** `openspec/changes/add-metrics/specs/metrics/spec.md` exists and no node or `cross_cutting_specs` entry maps `metrics`
- **THEN** `spec-mapping.unmapped` is reported for `metrics`

#### Scenario: spec.md only in the live change
- **WHEN** group `logging` is mapped, `openspec/specs/logging/` holds no `spec.md`, and `openspec/changes/add-logging/specs/logging/spec.md` exists
- **THEN** no spec-mapping finding is reported

#### Scenario: Live-change group without spec.md
- **WHEN** group `logging` is mapped, `openspec/specs/logging/` does not exist, and `openspec/changes/add-logging/specs/logging/` exists with no `spec.md` at any depth
- **THEN** `spec-mapping.no-spec-md` is reported for `logging`
