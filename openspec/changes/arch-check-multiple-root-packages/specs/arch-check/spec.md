## ADDED Requirements

### Requirement: A language has one root configuration form
Each language section SHALL set exactly one of `root_package` or `root_packages`. The legacy scalar form SHALL
retain its existing behavior. `root_packages` SHALL be a non-empty array of unique canonical relative paths.

#### Scenario: Legacy scalar remains compatible
- **WHEN** a language section sets `root_package: src`
- **THEN** the checker discovers sources and edges under `src` exactly as before

#### Scenario: Both configuration forms are rejected
- **WHEN** a language section sets both `root_package` and `root_packages`
- **THEN** `la-arch-check` exits 2 with a finding naming the required exclusive root configuration

#### Scenario: Missing configuration remains an error
- **WHEN** a language section sets neither root configuration form
- **THEN** `la-arch-check` exits 2 with a finding naming the required `root_package`

#### Scenario: TypeScript roots are combined
- **WHEN** a TypeScript section sets `root_packages: [app, packages/ui]` and both directories contain visible source
- **THEN** top-level units and imports are discovered in both directories, with module IDs relative to `source_root`

#### Scenario: Python roots are combined
- **WHEN** a Python section sets `root_packages: [service, shared]` and both directories contain Python modules
- **THEN** facts include units and runtime imports from both directory trees using the existing dotted module IDs

### Requirement: Configured roots are contained and disjoint
Each `root_packages` path SHALL resolve to a directory beneath `source_root` (defaulting to the repo root), including
after symlink resolution. Paths SHALL be pairwise disjoint; equal or nested roots SHALL be rejected. Invalid paths
and overlap SHALL produce a setup error naming the affected `root_packages` entries.

#### Scenario: Missing roots are rejected
- **WHEN** any configured root is absolute, contains a parent segment, is non-canonical, escapes by symlink, is not a directory, or the list is empty or contains duplicates
- **THEN** `la-arch-check` exits 2 with a finding naming `root_packages`

#### Scenario: Overlapping roots are rejected
- **WHEN** two configured roots are equal or one is nested under the other
- **THEN** `la-arch-check` exits 2 with a finding naming both conflicting `root_packages`

### Requirement: Facts cover the configured source union
Source discovery, top-level units, claims and runtime import measurement SHALL cover the union of configured roots.
Unit identifiers SHALL remain relative to `source_root`, with no configured-root rewriting. Architecture files and
OpenSpec specs SHALL remain relative to the repository root. Python and TypeScript twins SHALL produce equivalent
facts for equivalent layouts.

#### Scenario: Combined facts retain source-root-relative IDs
- **WHEN** a language section configures multiple roots below `source_root`
- **THEN** facts include all roots' units and import edges using IDs relative to `source_root`, and architecture documentation remains repo-root-relative
