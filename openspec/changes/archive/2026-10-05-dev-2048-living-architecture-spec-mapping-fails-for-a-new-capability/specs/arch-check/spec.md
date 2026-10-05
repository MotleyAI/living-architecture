## ADDED Requirements

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
