## Purpose

The architecture cross-check: code, the LikeC4 model, arc42 docs and OpenSpec specs agree, and the model is the
repo's single import law. This delta covers where source code is located relative to the repo root.

## ADDED Requirements

### Requirement: Source root is separate from the repo root
`architecture/index.yaml` MAY set `source_root`. This is a relative path from the repo root to the directory
that contains `root_package`; when absent it defaults to the repo root. All source discovery SHALL resolve
under `source_root`: claims, children, top-level units and import-edge measurement. Architecture files,
arc42 docs and OpenSpec specs SHALL resolve from the repo root. Module ids, and therefore findings, SHALL
NOT include the `source_root` prefix.

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
