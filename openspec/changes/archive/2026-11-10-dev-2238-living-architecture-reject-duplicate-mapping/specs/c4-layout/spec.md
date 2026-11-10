## ADDED Requirements

### Requirement: la-arch-migrate refuses an unusable index.yaml
When `la-arch-migrate` converts a model (`architecture/` holds a LikeC4 source file) and `architecture/index.yaml`
exists but is not valid UTF-8, not valid YAML (a duplicate key included) or not a mapping, it SHALL exit 2 writing
nothing, printing `la-arch-migrate: ` followed by the reason in the wording `la-arch-diagrams` uses for the same
index (`c4.index-invalid-yaml`, `c4.index-duplicate-key` or `c4.index-not-mapping`). A missing `index.yaml` SHALL
convert as before. Without a model to convert, the index SHALL NOT be read.

#### Scenario: Index not valid UTF-8
- **WHEN** an unversioned legacy repo's `architecture/index.yaml` is not valid UTF-8 and `la-arch-migrate` runs
- **THEN** it exits 2 printing `la-arch-migrate: index.yaml is not valid YAML`, and every file is byte-identical

#### Scenario: Index with a duplicate key
- **WHEN** an unversioned legacy repo's `architecture/index.yaml` repeats a key and `la-arch-migrate` runs
- **THEN** it exits 2 printing `la-arch-migrate: index.yaml is not valid YAML: ` followed by the duplicate-key
  message, and every file is byte-identical

#### Scenario: Index not valid YAML
- **WHEN** an unversioned legacy repo's `architecture/index.yaml` is not valid YAML and `la-arch-migrate` runs
- **THEN** it exits 2 printing `la-arch-migrate: index.yaml is not valid YAML`, and every file is byte-identical

#### Scenario: Index not a mapping
- **WHEN** an unversioned legacy repo's `architecture/index.yaml` holds a list and `la-arch-migrate` runs
- **THEN** it exits 2 printing `la-arch-migrate: index.yaml is not a mapping`, and every file is byte-identical
