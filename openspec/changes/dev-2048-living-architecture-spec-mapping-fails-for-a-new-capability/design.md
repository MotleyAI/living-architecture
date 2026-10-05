## Context

Spec-mapping read present groups only from `openspec/specs/`. A new capability reaches that folder only at
`openspec archive`, after every gate of the `/la:pr` flow has run.

## Goals / Non-Goals

**Goals:** a change that adds and maps a capability is green from the plan through archive.

**Non-Goals:** other arch-check checks; principle-tag forms such as `[enforced: lint:<rule>]`.

## Decisions

- **One set of present groups for all three checks.** Present = the subdirectories of `openspec/specs/` and of
  `openspec/changes/<id>/specs/` for every `<id>` directory except `archive`. Each group keeps every directory it
  was found in. `unmapped`, `dir-missing` and `no-spec-md` all read this set. Widening it only for `dir-missing`
  would let an unmapped new capability pass until archive and fail afterwards, the failure being fixed.
- **`no-spec-md` searches all of a group's directories**, recursively as before, and fires only if none holds a
  `spec.md`.
- **Location-neutral finding texts.** `unmapped` and `no-spec-md` name the group, not `openspec/specs/{group}`;
  `dir-missing` names both locations it searched.
- **Group name = top-level directory** under each `specs/` folder, as in the corpus today.

## Risks / Trade-offs

- Re-blessed goldens for every case printing a reworded finding (deliberate text change).
- New cases are Python-paired like the existing spec cases, so the npm twin is verified through
  `scripts/conformance-cross --twin typescript`.
