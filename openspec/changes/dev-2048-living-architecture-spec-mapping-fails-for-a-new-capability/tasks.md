## 1. Contract

- [ ] 1.1 In `shared/findings.yaml` set `spec-mapping.unmapped` to `'spec-mapping: spec group {group} is mapped by no node and not cross-cutting'`, `spec-mapping.dir-missing` to `'spec-mapping: {group} is mapped but has no spec dir in openspec/specs or a live change'`, `spec-mapping.no-spec-md` to `'spec-mapping: spec group {group} contains no spec.md'`; run `scripts/sync-shared` and verify `scripts/sync-shared --check` passes

## 2. Conformance cases (paired, `languages: [python]`, fixture `arch-ok`, extra files under the case's `repo/`)

- [ ] 2.1 `arch-check-spec-mapped-in-live-change`: remove `openspec/specs/logging`; add `openspec/changes/add-logging/specs/logging/spec.md`; exit 0
- [ ] 2.2 `arch-check-spec-mapped-only-archived`: remove `openspec/specs/logging`; add `openspec/changes/archive/2026-01-01-add-logging/specs/logging/spec.md`; exit 1, `dir-missing` for `logging`
- [ ] 2.3 `arch-check-spec-live-change-unmapped`: add `openspec/changes/add-metrics/specs/metrics/spec.md`; exit 1, `unmapped` for `metrics`
- [ ] 2.4 `arch-check-spec-md-in-live-change`: remove `openspec/specs/logging/spec.md` (directory kept, as in `arch-check-spec-dir-without-spec-md`); add `openspec/changes/add-logging/specs/logging/spec.md`; exit 0
- [ ] 2.5 `arch-check-spec-live-change-without-spec-md`: remove `openspec/specs/logging`; add a non-`spec.md` file under `openspec/changes/add-logging/specs/logging/`; exit 1, `no-spec-md` for `logging`
- [ ] 2.6 List 2.1–2.5 in `conformance/INVENTORY.md`
- [ ] 2.7 Write goldens with `LA_UPDATE_GOLDENS=1` for the new cases and re-bless every case printing a reworded finding; review the diff (only the three texts change in existing goldens)

## 3. Twins

- [ ] 3.1 `check_spec_mapping` in `python/src/living_architecture/archcheck/docs.py`: one present-groups map (group -> dirs) from the corpus and every non-`archive` change's `specs/`, used by all three checks; verify `uv run pytest -q` passes
- [ ] 3.2 `checkSpecMapping` in `node/src/archcheck/docs.ts`, identically; verify `npm test` and `npm run build && npm run conformance` pass, and `scripts/conformance-cross --twin typescript` passes the new cases

## 4. Docs

- [ ] 4.1 In `plugin/skills/living-architecture/SKILL.md` replace the bullet `every directory under openspec/specs/ appears exactly once: …` with `every spec group (a directory under openspec/specs/ or under a non-archived change's specs/) is mapped exactly once: in exactly one node's specs or in cross_cutting_specs:; every node named in a touches: list exists;` (backticks as in the surrounding text; approved wording)

## 5. Verify

- [ ] 5.1 Full suites green: `uv run pytest -q`, `uv run ruff check src tests`, `uv run basedpyright src tests` in `python/`; `npm run lint && npm run typecheck && npm test` in `node/`; `la-arch-check` on this repo
