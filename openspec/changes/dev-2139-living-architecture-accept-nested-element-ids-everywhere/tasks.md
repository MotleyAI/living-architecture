## 1. Shared contract

- [x] 1.1 `shared/schema/node.schema.json`: add `$defs/element` `{specs}`, drop `arc42` from `precise`/`virtual`; verify the schema tests in both twins.
- [x] 1.2 `shared/findings.yaml`: rename `spec-mapping.unknown-node` → `spec-mapping.unknown-element` (`{element}`); reword `spec-mapping.unmapped`, `arc42-exists.orphan`; remove `arc42-exists.node-doc-missing`, `arch-check.metadata-on-root`, `arch-check.metadata-on-nested`, `c4.include-non-top-level`, `c4.view-includes-non-top-level`; add `arch-check.arc42-key-retired`, `arc42-exists.nested-doc`, `arc42-exists.cross-cutting-not-flat`, `arc42-exists.cross-cutting-is-element`, `arch-migrate` move line and refusals (source missing, source moved twice, shared target, target taken, diagrams key taken) — texts exactly as in design.md / the spec deltas.
- [x] 1.3 `shared/cli.yaml`: `la-arch-migrate` help covers both steps.
- [x] 1.4 Run `scripts/sync-shared`; verify `scripts/sync-shared --check` and the drift tests pass.

## 2. Tests first (pr-tests stage)

- [x] 2.1 Neutral conformance cases, each listed in `conformance/INVENTORY.md`: nested `touches`; root `touches`; nested spec owner; root spec owner; element under a virtual node owning specs; unknown element (and unqualified `touches`); duplicate owners across root/node/nested/cross-cutting in one case (pins order and first/second); mapping key on a nested element; mapping key on a root; specs on a root; empty metadata on a nested element (now passes — rebless with that reason); retired `arc42` key on root, nested, precise and virtual elements; retired key beside an invalid key (ordering); nested element doc recognised; root doc recognised; element without a doc; orphan doc of a renamed element; nested doc at depth 1 and 2; symlinked file in a subfolder; symlinked directory not descended; broken symlink; several nested docs and orphans (code-point order); cross-cutting not flat; cross-cutting not flat and missing; cross-cutting is an element doc.
- [x] 2.2 Views cases (`la-arch-diagrams` / diagrams-fresh): nested include reach; overlapping includes; nested `X -> *` and `* -> X` anchors; anchor equal to an endpoint; descendant vs unrelated endpoints; self-edge collapse; legacy and non-legacy contributors collapsing to one edge; fully qualified name rejected; top-level-only views unchanged (existing goldens untouched).
- [x] 2.3 Migrate cases: canonical repo with `arc42` keys (doc moved, line removed, diagrams key renamed, other bytes unchanged incl. index.yaml comments); doc already at target; emptied virtual-node metadata block removed; cross-cutting doc flattened; legacy layout + arc42 key in one run; already current → nothing; refusals: missing source, source moved twice, shared target, target file taken (incl. a target that is another move's source), diagrams key taken; each leaves the repo unchanged.
- [x] 2.4 Unit tests in both twins for injected filesystem failures during the model rewrite, the index rewrite, each doc move and the combined legacy+arc42 run: every path byte-identical at its original location afterwards.
- [x] 2.5 Replace/remove the superseded cases `arch-check-arc42-node-doc-missing`, `arch-check-metadata-on-nested-element`, `arch-check-root-metadata-on-root`, `arch-check-spec-touches-unknown-node` (→ unknown-element) and every non-top-level include case; every `findings.yaml` template keeps at least one golden (verify with the template-coverage test).
- [x] 2.6 Mirror unit tests for the element map, spec mapping, arc42 docs and view expansion in `python/tests` and the node test suite.

## 3. Python twin

- [x] 3.1 `archcheck/nodes.py`: canonical element list (roots, nodes, nested) in declaration order; metadata validation by variety with the retired-key precedence; verify 2.1 metadata cases.
- [x] 3.2 `archcheck/docs.py`: spec ownership over all elements then `cross_cutting_specs`; `touches` against all element ids; arc42-exists per the new requirement with the layout walk rules; verify 2.1.
- [x] 3.3 `c4/views.py`: root-relative names at any depth, relative reach, subtree membership and anchor matching via one "is or descends from" predicate; verify 2.2 and existing diagram goldens unchanged.
- [x] 3.4 `c4/migrate.py`: two-step detection, global move plan with refusals, textual rewrites, staged verification, snapshot rollback; verify 2.3 and 2.4.

## 4. npm twin

- [x] 4.1 Port 3.1–3.4 to `node/src/archcheck/{nodes,docs}.ts`, `node/src/c4/{views,migrate}.ts`; verify `npm run lint && npm run typecheck`, `npm test`, `npm run build && npm run conformance`.

## 5. Skills, docs, version

- [x] 5.1 Apply the approved skill wording in design.md verbatim to `plugin/skills/{living-architecture,pr,pr-plan,pr-review,pr-implement,arch-init,arch-cleanup}/SKILL.md`; verify `npx -y @anthropic-ai/claude-code plugin validate plugin`.
- [x] 5.2 Grep `README.md`, `docs/` and `plugin/` for remaining `arc42 '` pointers, `<node>.arc42.md`, "touches unknown node" and `architecture/**/*.arc42.md`; any hit outside the approved wording is raised with the user before editing.
- [x] 5.3 Bump to 0.4.0 in `python/pyproject.toml`, `node/package.json`, `plugin/.claude-plugin/plugin.json`; re-run `scripts/sync-shared`; verify `la-doctor --contract-hash` agrees in both twins.

## 6. Gates

- [x] 6.1 Python: `uv run pytest -q`, `uv run ruff check src tests`, `uv run basedpyright src tests` green.
- [x] 6.2 `scripts/conformance-cross` green through both twins; `la-arch-check` green on this repo.

## 7. Declared format (merge of origin/main)

- [x] 7.1 Run the arc42 conversion as a step of the unversioned → 0.4.0 format migration (after the layout conversion, before the stamp) in both twins, through the format migration's journal; drop `— run la-arch-migrate` from `arch-check.arc42-key-retired`; take main's `arch-migrate.nothing`.
- [x] 7.2 Give every arc42 migrate case an unversioned `living-architecture.yaml` and the stamped (or, when refused, unchanged) config golden.
