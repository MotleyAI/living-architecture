## 1. Failing tests (pr-tests stage)

- [ ] 1.1 Runner case model (design D9): split `fixture_languages`, invoking twin and golden variant in `python/tests/test_conformance.py`; apply every listed overlay; select native cases per twin; accept a twin bin dir parameter. Verify that the existing corpus still passes unchanged through the PyPI twin.
- [ ] 1.2 Migrate every arch-check and arch-diagrams fixture and case to language roots (index sections, model wrapped in `python`, views `of python`, qualified `touches`). Regenerate only the arch-check goldens whose sole difference is qualified ids, and verify that every arch-diagrams golden and every diagram embedded in an arc42 fixture is byte-identical before and after (the D2 regression proof).
- [ ] 1.3 New Python-twin cases (failing until implemented): index sections, `x-` keys, legacy `nodes`/`root_package`/unknown keys, no language section, root-element rules (undeclared top-level, missing root, metadata on root), root-relative relations (wrapped text, root-prefixed endpoint, same local ids in two roots, relation outside roots, relation in node body), scoped views (unscoped, `of` a non-root), qualified ids in every template containing `{node}`, `{element}`, `{src}` or `{dst}` (audit list in the case notes), `[lang:]` tags (declared, undeclared, duplicate, malformed), non-ASCII target id.
- [ ] 1.4 TS adapter cases (`node/` overlays, kind paired/adapter), one per rule in the specs "TypeScript units", "TypeScript import edges" and "TypeScript module resolution": directory/file/ambiguous units (declared and derived), invisible test/`.d.ts`/`node_modules` files, root barrel, directories without sources, symlinks inside/escaping/cyclic, every edge form and the type-only decision table (design D6) incl. mixed specifiers, `paths`/`baseUrl`, `moduleResolution` node16/nodenext/bundler, `.js`→`.ts`, index barrels, `tsconfig` key vs nearest-up vs none, `extends`, project references (solution-style root, nested, overlapping includes, cycle, `rootDir`/`outDir`/`declarationDir`, `.mts`/`.cts`, missing/stale outputs), allowJs-off repos with `.js` units, externals (npm, `node:`, subpath), unresolved relative incl. `..`, `?`/`#` suffix and escape. Plus the TS model-truth set: missing edge, dead, shadowed, legacy count.
- [ ] 1.5 Multi-language cases (`languages: [python, typescript]`): disjoint roots clean, arrow measured only in its language → dead, union witness choice, fixed output order, mixed claims findings.
- [ ] 1.6 Forwarding cases: `la-doctor --twin` line and hidden from help, shadowed twin found, version or contract mismatch skipped, runner probe success (fake `npx`/`uvx` on PATH) and failure → exit 2 hint, runner absent → exit 2 hint, wholesale forward of each Python-only command through the npm twin, neutral commands never forward with the twin hidden, facts request for a non-owned language → 2, forwarded setup error relayed, malformed/schema-invalid/wrong-identity facts → 2, `LA_FORWARDED=1` refusal.
- [ ] 1.7 Shared vectors: TypeScript test-file classification set; YAML profile expansion (booleans, nulls, sexagesimal, numeric formats, timestamps, merge keys, nested duplicates, non-string keys); facts-schema accept/reject documents. Python tests consume them and fail where unimplemented.
- [ ] 1.8 Node-side Vitest tests (failing): every shared vector, manifest parser vectors (abbreviation, `--`, passthrough, `require_one_of`, choices, nargs, repeatable, internal options), `bin` set equals the manifest, snapshot drift, version lockstep across `node/package.json`, `python/pyproject.toml` and `plugin.json`.
- [ ] 1.9 Codex review of the tests against the plan (pr-tests Step 2). Verify that the findings are resolved with the user.

## 2. Shared contract

- [ ] 2.1 `schema/index.schema.json`: language sections (`root_package`, `source_root`, TS `tsconfig`), `patternProperties` `^x-`, at least one language section, no top-level `root_package`/`source_root`. Verify with the index-schema cases from 1.3.
- [ ] 2.2 `schema/facts.schema.json` (design D3). Verify the facts vectors from 1.7.
- [ ] 2.3 `languages.yaml`: `typescript` entry (source extensions, test globs, runner, install command); runner and install command for `python`. `cli.yaml`: per-command native languages, internal `la-doctor --twin`, internal `la-arch-check --language`/`--emit`. `findings.yaml`: new templates (root-structure errors, relation outside roots, view scoping, ambiguity ×2, `[lang:]` unknown, twin unavailable, facts protocol failure, forward refused). `regex-subset.md`: the non-ASCII rule. Run `scripts/sync-shared` (now also into `node/`) and verify the drift tests.

## 3. PyPI twin

- [ ] 3.1 `c4`: language roots, root-relative relations, model-level relation finding, scoped views via a root-local projection (design D2). Verify the 1.2 byte-identity check and the c4 cases from 1.3.
- [ ] 3.2 `archcheck`: index sections and layout per language, root-element rules, qualified ids, facts-based claims math, union model-truth, fixed output order, `x-` keys, `[lang:]` tags, non-ASCII target ids; `license()` on qualified ids with native module inputs. Verify the 1.2/1.3/1.5 cases through the PyPI twin.
- [ ] 3.3 `lang`: the Python facts provider (unit statuses, top-level units, sorted witnessed edges). Verify the Python arch-check cases.
- [ ] 3.4 New `twin` node: identity handshake, PATH discovery, runner probe, wholesale forwarding, facts request + schema validation, `LA_FORWARDED`; `doctor --twin`; `cli` internal options. Verify the 1.6 cases through the PyPI twin.

## 4. npm twin

- [ ] 4.1 Scaffold `node/` (design D8): package.json (`private`, engines, deps `typescript@~6.0`, `yaml`, `ajv`; dev deps Vitest, ESLint, typescript-eslint, `@types/node`), package-lock, tsconfig, ESLint config, build script copying contract data and generating one bin per manifest command. Verify `npm ci && npm run build && npm run lint` succeed and the bin-set test passes.
- [ ] 4.2 `contract`: snapshot loading, renderer with canonical repr, glob dialect, default materialization, YAML 1.1 profile, regex-subset check, JSON Schema validation. Verify every shared vector test.
- [ ] 4.3 `cli` (manifest parser and dispatch), `config`, `doctor` (incl. `--twin`, `--contract-hash`), `review` shims. Verify the neutral `la-config`, `la-doctor` and review-shim cases through the npm twin.
- [ ] 4.4 `c4`: constrained LikeC4 parser with metadata, roots, root-relative relations, scoped views, mermaid. Verify every `la-arch-diagrams` case and the c4 cases through the npm twin.
- [ ] 4.5 `lang`: TS adapter (design D6). Verify every 1.4 case through the npm twin.
- [ ] 4.6 `archcheck` (neutral checks, facts, union model-truth, ordering) and `twin`. Verify the 1.2–1.6 arch-check and forwarding cases through the npm twin.

## 5. Conformance, CI and publish

- [ ] 5.1 `scripts/conformance-cross` and `npm run conformance`. Verify that every case passes through both twins' entry points.
- [ ] 5.2 CI: node job (npm ci, lint, typecheck, Vitest, build, native conformance), npm pack smoke test outside the checkout (la-doctor contract hash equal to the PyPI twin's, la-config show, a review shim against the fake gh), cross-twin job; third-party actions pinned by SHA. Verify the scripts locally.
- [ ] 5.3 Publish workflow: pre-check equal contract hashes and both versions equal to the tag, else publish neither; npm job with trusted publishing that logs a skip while `"private": true`. Verify with `actionlint` (or a dry read) and a local run of the pre-check script.

## 6. This repo's architecture (every edit presented for the user's per-edit approval)

- [ ] 6.1 Present and write `architecture/index.yaml`: `python: {source_root: python/src, root_package: living_architecture}`, `typescript: {source_root: node, root_package: src}`; `arch-check` and `twin-forwarding` specs as `cross_cutting_specs` touching both twins' owning nodes (at archive time, when the spec dirs exist); `shared-contract` touches qualified. Verify `la-arch-check` from both twins.
- [ ] 6.2 Present and write `architecture/model/la.c4`: roots `python` (ten nodes + `twin`) and `typescript` (contract, config, cli, c4, archcheck, lang, review, doctor, twin), mirrored arrows plus `cli -> twin`, `archcheck -> twin`, `twin -> contract`. Verify `npx likec4 validate architecture` and `la-arch-check` from both twins.
- [ ] 6.3 Present and write `architecture/views.c4` (`view system of python`, a typescript view) and `system.arc42.md` (both views embedded; second `[enforced: test:…]` on principle 1 for the Node-side conformance entry); run `la-arch-diagrams`. Verify `la-arch-check` exits 0 from both twins.

## 7. Docs and skills

- [ ] 7.1 `AGENTS.md` (node dev/test commands, `npm run conformance`, `scripts/conformance-cross`, forwarding), `README.md` (npm twin, index sections, migration), `conformance/README.md` (case model) and `INVENTORY.md`, the `living-architecture` and `arch-slice` skills (language roots, scoped views, root-relative relations, `x-` keys, migration steps). Verify `test_skills`, `plugin validate plugin`, and every new findings id covered by a golden.

## 8. Final gates

- [ ] 8.1 `python/`: full non-integration suite, `ruff check src tests`, `basedpyright src tests`. `node/`: lint, typecheck, Vitest, conformance. Cross-twin run. Verify all green.
- [ ] 8.2 `la-check-conventions --base main` clear; `openspec validate dev-2025-living-architecture-npm-twin-of-the-core-ts-arch-check-units --strict` passes; `la-arch-check` exits 0 from both twins on this repo.
