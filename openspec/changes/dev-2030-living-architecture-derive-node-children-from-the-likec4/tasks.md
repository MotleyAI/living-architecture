## 1. Shared contract

- [ ] 1.1 Add `shared/schema/node.schema.json` with `$defs/precise` and `$defs/virtual` (design D2); remove `nodes` and the node `$defs` from `index.schema.json`; verify `uv run pytest -q` contract-schema tests
- [ ] 1.2 `shared/findings.yaml`: remove `model-identity.node`/`.child`/`.element`, `model-identity` from `check_ids`, `claims-exactly-once.child-twice`; reword `claims-exist.child-missing` → `'claims-exist: element {element} maps to {unit}, which does not exist on disk'`, `claims-exactly-once.child-collides` → `'claims-exactly-once: element {element} ({unit}) collides with declared unit {clash}'`, `claims-exist.virtual-children` → `'claims-exist: virtual node {node} may not contain elements'`; add `arch-check.metadata-invalid: 'model element {element}: {error}'`, `arch-check.metadata-on-nested: 'model element {element}: nested elements may not carry metadata'`, `c4.malformed-metadata: 'element {element} has malformed metadata: {line}'`; verify every template is produced by a golden
- [ ] 1.3 Run `scripts/sync-shared`; verify `scripts/sync-shared --check` and the drift test pass

## 2. Python twin

- [ ] 2.1 `c4/model.py`: parse `metadata { }` as an explicit state (design D1) into `Element.metadata`; metadata problems in `ModelParse.metadata_findings`, never `c4.unrecognized-model-line`; `la-arch-diagrams` refuses on them; verify parser unit tests (blocks before/between/after nested elements, multi-line array, unclosed array, repeated key, second block, double quotes)
- [ ] 2.2 `archcheck`: canonical node/unit builder (design D3) with schema validation by kind and escalation to `ArchCheckError` (design D5); verify unit tests for each malformed-metadata scenario
- [ ] 2.3 Port claims (incl. derived-unit existence, collisions per design D4, virtual-children), arc42-exists, spec-mapping, model-truth and `license()` to the builder; delete `check_model_identity`, `check_children`, `_declared_children` and every `index["nodes"]` read; verify `uv run pytest -q`
- [ ] 2.4 Update `python/tests/test_arch_check.py` / `test_arch_diagrams.py` for the new format; verify `uv run ruff check src tests` and `uv run basedpyright src tests` are clean

## 3. Conformance

- [ ] 3.1 Migrate every fixture and case: `nodes:` → model metadata (model overlay where a case varied a node); verify every golden not listed in 3.2–3.3 is byte-identical without `LA_UPDATE_GOLDENS`
- [ ] 3.2 Deliberate golden changes (reason: behaviour change): `arch-check-claims-child-missing`, `arch-check-claims-child-collides`, `arch-check-claims-virtual-children` (reworded); `arch-check-identity-element-unmapped` split into `core.inner` → `child-missing` and an unmapped `orphan` → setup error; `arch-check-identity-no-model-files` (unclaimed units, no identity findings); delete `arch-check-identity-node-not-in-model`, `arch-check-identity-child-not-in-model`, `arch-check-claims-child-twice`
- [ ] 3.3 New cases, one per arch-check spec scenario not yet covered: model child governed with no index entry (child-level `missing-edge` + live child arrow), grandchild governed, grandchild missing, descendants not colliding, descendant colliding with another node's package, multi-line array, virtual-kind element nested under a precise node, `nodes:` in index.yaml (exit 2, contains `nodes`), precise node without package, unknown key, scalar `claims`, `packages` on precise, `package`/`claims` on virtual, metadata on nested element, repeated key, second block, malformed syntax (arch-check exit 2; arch-diagrams `c4.malformed-metadata`), enforced tag naming `model-identity` → `unknown-id`; schema wording pinned with `contains` (element + key); verify the corpus passes
- [ ] 3.4 Update `conformance/INVENTORY.md` (rows for the above; move the "non-list `children`/`claims`/`specs`" crash exclusion into covered setup errors); verify the inventory test

## 4. This repo and docs

- [ ] 4.1 `architecture/model/la.c4`: each node gets `metadata { package 'living_architecture.<id>' }`, `archcheck` also `specs ['arch-check']`; `architecture/index.yaml`: delete `nodes:` (both edits approved in pr-plan); verify `uv run la-arch-check` is OK
- [ ] 4.2 Run `npx likec4 validate` on `architecture/` and on the migrated `arch-ok` fixture to confirm the metadata subset is valid LikeC4 (manual, needs network)
- [ ] 4.3 `plugin/skills/living-architecture/SKILL.md`, `plugin/skills/arch-slice/SKILL.md`, `README.md`: new format, law text, short manual "migrate `nodes:` into model metadata" procedure (design Migration Plan); verify no `children:`/`nodes:` examples remain and `npx -y @anthropic-ai/claude-code plugin validate plugin` passes

## 5. Final gate

- [ ] 5.1 Full `uv run pytest -q`, ruff, basedpyright, `scripts/sync-shared --check`, `uv run la-arch-check`, `openspec validate dev-2030-living-architecture-derive-node-children-from-the-likec4 --strict` all green; PR targets `main`
