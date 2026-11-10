## ADDED Requirements

### Requirement: A language has one root configuration form
Each language section SHALL set exactly one of `root_package` or `root_packages`. The legacy scalar form SHALL
retain its existing behavior. `root_packages` SHALL be a non-empty array of unique canonical relative paths. Every
root-configuration error SHALL be a setup error reported with a shared finding before schema validation, so both
twins print the same text.

#### Scenario: Legacy scalar remains compatible
- **WHEN** a language section sets `root_package: src`
- **THEN** the checker discovers sources and edges under `src` exactly as before

#### Scenario: Both configuration forms are rejected
- **WHEN** a language section sets both `root_package` and `root_packages`
- **THEN** `la-arch-check` exits 2 with a finding naming the required exclusive root configuration

#### Scenario: Missing configuration remains an error
- **WHEN** a language section sets neither root configuration form
- **THEN** `la-arch-check` exits 2 with a finding naming the required `root_package`

#### Scenario: Malformed scalar keeps its finding
- **WHEN** a language section sets `root_package` to an empty string or a non-string
- **THEN** `la-arch-check` exits 2 with the same finding as a missing `root_package`

#### Scenario: TypeScript roots are combined
- **WHEN** a TypeScript section sets `root_packages: [app, packages/ui]` and both directories contain visible source
- **THEN** top-level units and imports are discovered in both directories, with module IDs relative to `source_root`

#### Scenario: Python roots are combined
- **WHEN** a Python section sets `root_packages: [service, shared]` and both directories contain Python modules
- **THEN** facts include units and runtime imports from both directory trees using the existing dotted module IDs

### Requirement: Configured roots are contained and disjoint
Each `root_packages` path SHALL resolve to a directory beneath `source_root` (defaulting to the repo root), including
after symlink resolution; all roots of a section SHALL share its one `source_root`. Paths SHALL be pairwise
disjoint; equal (including a repeated entry) or nested roots SHALL be rejected. Invalid paths and overlap SHALL
produce a setup error naming the affected `root_packages` entries.

#### Scenario: Invalid roots are rejected
- **WHEN** `root_packages` is not a non-empty list of non-empty strings, or any configured root is absolute, contains a parent segment, is non-canonical, escapes by symlink, or is not a directory
- **THEN** `la-arch-check` exits 2 with a finding naming `root_packages`

#### Scenario: Overlapping roots are rejected
- **WHEN** two configured roots are equal (including a repeated entry) or one is nested under the other
- **THEN** `la-arch-check` exits 2 with a finding naming both conflicting `root_packages`

### Requirement: Facts cover the configured source union
Source discovery, top-level units, claims and runtime import measurement SHALL cover the union of configured roots.
Unit identifiers SHALL remain relative to `source_root`, with no configured-root rewriting. Architecture files and
OpenSpec specs SHALL remain relative to the repository root. Python and TypeScript twins SHALL produce equivalent
facts for equivalent layouts.

#### Scenario: Combined facts retain source-root-relative IDs
- **WHEN** a language section configures multiple roots below `source_root`
- **THEN** facts include all roots' units and import edges using IDs relative to `source_root`, and architecture documentation remains repo-root-relative

## MODIFIED Requirements

### Requirement: Source root is separate from the repo root
Each language section of `architecture/index.yaml` MAY set `source_root`. This is a relative path from the repo
root to the directory that contains that section's roots (`root_package` or `root_packages`); when absent it
defaults to the repo root. All source discovery for a language SHALL resolve under its `source_root`: claims,
model-derived child units, top-level units and import-edge measurement. Architecture files, arc42 docs and OpenSpec
specs SHALL resolve from the repo root. Module ids, and therefore findings, SHALL NOT include the `source_root`
prefix.

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

### Requirement: index.yaml carries only repo-wide settings
`architecture/index.yaml` SHALL NOT declare nodes. Its keys SHALL be one section per declared language, keyed by
a language id of the shared languages registry (`python`, `typescript`), plus `cross_cutting_arc42`,
`cross_cutting_specs`, `legacy_arrows`, `diagrams` and `view_depth`, plus any number of repo-owned keys starting
with `x-`, which the tools SHALL ignore. A language section SHALL hold exactly one of `root_package` and
`root_packages` and MAY hold `source_root`; the `typescript` section MAY also hold `tsconfig`. At least one
language section SHALL be present; `x-` keys do not count. An `index.yaml` carrying `nodes`, a top-level
`root_package` or `source_root`, or any other unknown key SHALL be a setup error naming the key.

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

### Requirement: Each declared language has one root element
For each language section of `index.yaml` the model SHALL have exactly one top-level element whose id equals the
language id, of any element kind; it is that language's root, and it stands for the section's configured roots. A
root SHALL carry no mapping keys and MAY carry `specs`. A top-level element whose id is not a declared language, a
declared language with no root element, and a mapping key on a root SHALL each be a setup error (exit 2) naming the
element or language.

#### Scenario: Single-language model
- **WHEN** `index.yaml` declares only `python` and the model wraps every node in `python = system 'App' { ... }`
- **THEN** the nodes are checked against the `python` section's configured roots

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

### Requirement: TypeScript units
A TypeScript unit SHALL be an extensionless path relative to the section's `source_root`. It SHALL exist iff it
names a directory containing at least one visible source file at any depth, or exactly one visible module file
`<unit>.<ext>` with `<ext>` among `.ts .tsx .mts .cts .js .jsx .mjs .cjs`. A unit naming both such a directory
and a module file, or module files with more than one extension, SHALL be ambiguous and yield a `claims-exist`
ambiguity finding listing the sorted candidate paths (one template for declared units, one for derived elements).
Visible source files SHALL exclude files matching the shared TypeScript test globs, `*.d.ts` files, and anything
under a `node_modules` directory. Symlinks SHALL be followed only while their real path stays under the section's
`source_root`. The top-level units SHALL be, for each configured root, every visible source file directly under it
other than its barrel `<root>/index.<ext>`, and every directory directly under it that contains a visible source
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

### Requirement: TypeScript module resolution
Specifiers SHALL be resolved with the compiler options of the repo's tsconfig: the section's `tsconfig` when set
(repo-relative), else, for the sources of each configured root, the nearest `tsconfig.json` from
`<source_root>/<root>` up to the repo root, else the TypeScript defaults with `moduleResolution: bundler`.
Resolution SHALL honour `paths`, `baseUrl`, `moduleResolution`, `.js` specifiers naming `.ts` sources, directory
index files and project references, and SHALL resolve JavaScript files even when the tsconfig disables `allowJs`.
With project references, each file SHALL resolve with the options of the first project, in depth-first reference
order, whose file list contains it, else the root config's; reference cycles SHALL be tolerated. A resolution to a
referenced project's emitted declaration file SHALL be mapped to the source that emits it. tsconfig files SHALL be
read, never executed.
Classification:
- a target whose real path lies under one of the section's roots is internal and attributes to its element;
- a Node builtin, a target resolved into `node_modules`, and an unresolved bare specifier are external (no edge);
- a target whose real path lies outside every root is unattributed (no edge);
- an unresolved relative specifier is attributed lexically: the importer's directory joined with the specifier,
  normalized, with a trailing `?…`/`#…` suffix and a known source extension stripped, and unattributed if it
  leaves every root.

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

#### Scenario: Each root uses its own tsconfig
- **WHEN** no `tsconfig` key is set and the roots `app` and `lib` each hold a `tsconfig.json` with its own `paths` alias
- **THEN** each root's imports resolve under its own tsconfig's aliases
