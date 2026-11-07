## 1. Contract and decision

- [x] 1.1 Add exclusive legacy `root_package` / new non-empty `root_packages` config contract and shared diagnostics; `scripts/sync-shared` refreshed both runtime snapshots.
- [x] 1.2 Document slash-path configuration, Python dotted IDs, disjointness, union discovery, legacy compatibility, and the unpublished-change adoption boundary.

## 2. Twins

- [x] 2.1 Resolve each root under `source_root`, validate directories and symlink containment, reject duplicates/overlap, and retain single-root constructor compatibility in both twins.
- [x] 2.2 Combine source discovery, top-level units, import targets, and top-level facts across roots; IDs remain relative to `source_root`.
- [x] 2.3 Add Python/TypeScript tests for combined roots, nested paths, malformed/empty/duplicate lists, missing directories, symlink escape, overlap, and scalar compatibility.

## 3. Conformance and adoption

- [x] 3.1 Add positive multi-root facts cases for Python and TypeScript, invalid configuration cases, inventory entries, and synchronized contract snapshots.
- [x] 3.2 Focused validation: Python arch-check/contract tests passed (857); Python conformance cases passed (20); TypeScript conformance case passed (5 run); Node unit tests passed (74), Node typecheck and build passed, Ruff/basedpyright passed (0 diagnostics), targeted ESLint passed, strict OpenSpec and architecture-scoped LikeC4 validation passed, `scripts/sync-shared --check` and `git diff --check` passed. Whole-repo LikeC4 discovery includes conformance fixture models and reports their known duplicate definitions, so validation was correctly scoped to `architecture/`.
- Follow-up on 7 Nov 2026: extracted per-root validation and resolved-path overlap checks from TypeScript `resolveLayout` after review feedback. Node unit tests passed (995 across 26 files), the TypeScript twin shared conformance suite passed (2,493 cases), TypeScript typecheck/build and lint passed, the focused convention gate reported zero violations (7.5% text-only ratio), and `git diff --check` passed. The overlap and root-diagnostic cases remain covered by `index-file.test.ts`.
- Follow-up on 7 Nov 2026: both twins now reject malformed `root_packages` values (scalar, empty list, or non-string member) with one shared diagnostic, including direct resolver calls. The focused TypeScript unit suite passed (21), Python arch-check suite passed (222), and the new conformance cases passed through each twin (5 runs per twin). Node typecheck/lint/build, Python Ruff, strict OpenSpec validation, shared-contract check, and diff check passed. A whole conformance run overlapped the Node rebuild and also exposed missing installed peer-twin commands; its failures were not used as evidence, so validation was repeated after the build on the new cases only.
- [ ] 3.3 Revisit Operalta architecture configuration and LikeC4 mappings using the new published contract; do not enable enforcement until all source roots and package mappings are represented and checked.
