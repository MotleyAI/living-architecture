## MODIFIED Requirements

### Requirement: TypeScript refactors are computed per project
The TypeScript `dr-refactor` SHALL load the tsconfig named by `index.yaml`'s `typescript.tsconfig` when set;
otherwise, as TypeScript's own tooling does, it SHALL look at the `tsconfig.json` files from the source file's
directory up to `<project>` and take the outermost one whose reference graph contains the file (a solution
config), else the nearest one. It SHALL load every project in that reference graph, each with its own compiler
options. `dr-compliance` and `dr-mock-lint` SHALL pick each input file's tsconfig the same way.
An `architecture/index.yaml` that exists but is not valid UTF-8 or not valid YAML SHALL be an error, never a reason
to fall back: a duplicate key SHALL be reported with the `c4.index-duplicate-key` wording, any other problem with
the `c4.index-invalid-yaml` wording, and the command SHALL exit as for a named tsconfig that does not exist. Only a
missing `index.yaml`, or one that names no tsconfig, SHALL fall back.
A source file SHALL belong to the first project in depth-first preorder that contains it; a file in no project
SHALL exit 1. A rename SHALL be computed in every project that contains or references the owning project;
identical edits SHALL be merged, and differing edits to one span SHALL exit 1. The whole change set SHALL be
computed and validated before any write: overlapping edits, a move onto an existing path, or a missing
destination SHALL exit 1 with nothing written. A dry-run SHALL never write. The TypeScript used SHALL be the
twin's bundled one; target-repo code SHALL never be loaded.

#### Scenario: Rename across project references
- **WHEN** a solution tsconfig references `core` and `app`, `app` imports `foo` from `core`, and `foo` is renamed in `core`
- **THEN** the edits in both projects are printed

#### Scenario: tsconfig below the project root
- **WHEN** `index.yaml` names no tsconfig, `<project>` has no `tsconfig.json`, and `web/tsconfig.json`
  includes `web/src`
- **THEN** `dr-refactor` and `dr-compliance` on `web/src/a.ts` use `web/tsconfig.json`'s project and options

#### Scenario: Duplicate key in the index
- **WHEN** `architecture/index.yaml` repeats a key and `dr-refactor`, `dr-compliance` or `dr-mock-lint` runs on a TS
  file
- **THEN** it prints `index.yaml is not valid YAML: ` followed by the duplicate-key message, exits as for a missing
  named tsconfig (1 for `dr-refactor`, 2 for `dr-compliance` and `dr-mock-lint`) and writes nothing

#### Scenario: Invalid index YAML
- **WHEN** `architecture/index.yaml` is not valid YAML or not valid UTF-8 and `dr-refactor` runs on a TS file
- **THEN** it prints `index.yaml is not valid YAML`, exits 1 and writes nothing

#### Scenario: Projects with different compiler options
- **WHEN** `app` uses a `paths` alias that `core` does not declare
- **THEN** the alias import in `app` is rewritten by the rename

#### Scenario: File outside every project
- **WHEN** `--file` names a TS file no project includes
- **THEN** it exits 1 with the outside-project finding

#### Scenario: Move onto an existing file
- **WHEN** `--apply move-module --module src/a.ts --dest lib` runs and `lib/a.ts` exists
- **THEN** it exits 1 with the collision finding and no file changes
