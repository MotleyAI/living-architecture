## 1. Shared contract

- [x] 1.1 Add to `shared/`: the LikeC4 source-extension constant (`.c4`, `.likec4`); finding/message templates for every layout violation kind (missing, not a file, stray, missing/duplicate/disallowed block, unexpected top-level text, unbalanced braces), the layout message header, the `la-arch-migrate` hint, the manual-merge tail, and `la-arch-migrate` outputs (written, deleted, nothing to migrate, not migratable, verification mismatch, error); remove `c4.no-views-block`. Verify: `scripts/sync-shared --check` passes after sync.
- [x] 1.2 Declare `la-arch-migrate` in `shared/cli.yaml` (`--root`, exit `{0: migrated or nothing to migrate, 2: not migratable, verification mismatch or filesystem error}`) and add its vectors to `shared/vectors/cli.yaml`; leave `la-arch-diagrams` exit contract unchanged. Verify: CLI contract vector tests pass in both twins.

## 2. Tests first (pr-tests stage)

- [x] 2.1 Conformance cases (both twins) for every `c4-layout` scenario: canonical, missing model/views, canonical path is a directory, stray `.c4`, stray `.likec4`, nested stray, uppercase extension ignored, symlinked stray, each block rule, braces in strings/comments, all-violations-in-one-message ordering, legacy hint, non-migratable manual-merge message, index-error precedence, top-level facts ignoring layout, `la-arch-diagrams` exit 1 on a violation. Verify: cases listed in `conformance/INVENTORY.md`; every new `findings.yaml` template produced by ≥1 golden.
- [x] 2.2 Conformance cases (both twins) for every `la-arch-migrate` scenario: multi-file, single file (`model/model.c4`), views created when absent, comments/blank lines outside blocks, inline comment on a block's opening line, parse findings carry over, non-`.c4` file keeps `model/`, already canonical, not migratable (stray file; legacy file with a `views` block; top-level text), migrated repo reports the same `la-arch-check` findings, write-failure rollback (read-only dir). Verify: listed in INVENTORY.md.
- [x] 2.3 Unit tests (pytest + Vitest) for migrate failure injection at every write / unlink / rmdir boundary (all legacy bytes, the directory and a pre-existing `views.c4` restored; only created files removed) and for the verification-mismatch guard (nothing written, exit 2). Verify: tests fail before implementation.
- [x] 2.4 Update scaffold cases for the new output (`architecture/model.c4` with one `specification` + one `model` block holding every root) and refusal set (canonical model, legacy `model/app.c4`, nested `.likec4`, first clash in code-point order); rewrite the arch-check "no model files" case to "model without roots". Verify: goldens reviewed and edited by hand (`golden: manual`) or regenerated with a stated reason.
- [x] 2.5 Classify every existing fixture by intent (layout-incidental vs layout-testing). Mechanically migrate incidental ones (`architecture/model/*.c4` → merged `architecture/model.c4`, plus a minimal `views.c4` where an arch-check/diagrams outcome is pinned) with goldens byte-identical; rewrite layout-testing ones (`arch-check-identity-no-model-files`, `arch-scaffold-existing-*`, `arch-diagrams-no-views-file`, `arch-check-parse-views-no-views-block`, …) deliberately. Verify: no golden diff in incidental fixtures; `find conformance -path '*architecture/model/*.c4'` lists only deliberate legacy-layout fixtures.
- [x] 2.6 Packaging smoke tests: `la-arch-migrate` is an installed command of the PyPI wheel (`python/tests/test_packaging.py`) and the npm pack. Verify: tests fail before registration.

## 3. Implementation — Python twin

- [x] 3.1 `c4` layout module: source discovery (decision 4), top-level block scanner (decision 3), classification and the single layout message (decision 2). Verify: the 2.1 cases pass through the PyPI twin.
- [x] 3.2 `parse_model` reads only `architecture/model.c4`, `parse_views` only `architecture/views.c4`; drop the `architecture/model/` glob and the `c4.no-views-block` path. Verify: no code outside the migrator references `architecture/model/`.
- [x] 3.3 `la-arch-check` runs the layout check after `index.yaml` validation and before any model read (not for `--emit facts --top-level`), exit 2; `la-arch-diagrams` runs it first, exit 1. Verify: 2.1 cases pass.
- [x] 3.4 Scaffold writes `architecture/model.c4` + `views.c4` and refuses on any LikeC4 source under `architecture/` (first clash in code-point order). Verify: 2.4 cases pass.
- [x] 3.5 `la-arch-migrate` in `c4` (merge, verify, transaction per decisions 6–8) and its CLI entry; register in `python/pyproject.toml` scripts and the CLI module. Verify: 2.2, 2.3, 2.6 pass.

## 4. Implementation — npm twin

- [x] 4.1 Port 3.1–3.5 to `node/src/c4`, `node/src/archcheck`, `node/src/cli` with the shared code-point comparator; add the `la-arch-migrate` bin to `node/package.json` and the CLI dispatch. Verify: `npm run lint && npm run typecheck`, `npm test`, `npm run build && npm run conformance` pass.
- [x] 4.2 Cross-twin run. Verify: `scripts/conformance-cross` passes for every case.

## 5. This repo's architecture (each edit needs the user's explicit OK of the exact diff)

- [x] 5.1 Run `la-arch-migrate` on this repo (`architecture/model/la.c4` → `architecture/model.c4`); present the resulting diff for approval before keeping it. Verify: `la-arch-check` from both twins prints `arch_check: OK`.
- [x] 5.2 Add `specs ['c4-layout']` to `python.c4`'s metadata in `architecture/model.c4`; present the exact edit for approval. Verify: no `spec-mapping` finding for `c4-layout`. Gotcha: until this lands, `la-arch-check` on this repo reports `spec-mapping: spec group c4-layout is mapped by no node` (the live change's spec counts as present) — expected, not a regression.

## 6. Docs and skills

- [x] 6.1 `plugin/skills/living-architecture/SKILL.md`: the two-file layout, block rules, `la-arch-migrate`; `plugin/skills/arch-init/SKILL.md`: scaffold writes the two files; `plugin/skills/pr/SKILL.md`: name `architecture/model.c4` and `architecture/views.c4` instead of `architecture/**/*.c4`; README/docs wherever they describe the layout. Verify: `grep -rn "model/" plugin docs README.md` finds no legacy-layout description outside the migration docs; `npx -y @anthropic-ai/claude-code plugin validate plugin` passes.

## 7. Final verification

- [x] 7.1 Full suites: `uv run pytest -q` (python/), ruff, basedpyright, `npm run lint && npm run typecheck && npm test`, `npm run build && npm run conformance`, `scripts/sync-shared --check`, `la-arch-check`. Verify: all green.
