# Conformance inventory

Every output and exit branch of every command, as of the pre-restructure tool, mapped to the case(s) under
`cases/` that pin it. `tests/test_conformance.py` checks that every case is listed here and every listed id
exists. Cases marked *(new)* pin behaviour introduced by this change; their goldens are hand-written.

## la-arch-check

| Branch | Exit | Cases |
|---|---|---|
| clean model | 0 | `arch-check-ok`, `arch-check-claims-child-module-file`, `arch-check-diagrams-fresh`, `arch-check-parse-spec-inline-statements`, `arch-check-parse-views-absent`, `arch-check-spec-nested-spec-md-counts`, `arch-check-spec-no-openspec-dir-nothing-mapped`, `arch-check-tags-fences`, `arch-check-tags-id-on-next-line` |
| repo root: `--root`, `.git` discovery from a subdir, no `.git` (cwd) | 0 | `arch-check-root-flag`, `arch-check-root-discovery-from-subdir`, `arch-check-root-without-git-is-cwd` |
| `index.yaml` missing (OSError) | 2 | `arch-check-index-missing` |
| `index.yaml` invalid YAML | 2 | `arch-check-index-invalid-yaml` |
| *(new)* `index.yaml` top level not a mapping | 2 | `arch-check-index-not-mapping` |
| `root_package` absent / empty / not a string | 2 | `arch-check-root-package-absent`, `arch-check-root-package-empty`, `arch-check-root-package-not-string` |
| `root_package` dir missing (layout validation) | 2 | `arch-check-root-package-dir-missing` |
| invalid `living-architecture.yaml` | 2 | `arch-check-config-invalid`, `arch-check-config-invalid-regex` |
| *(new)* `nodes` in `index.yaml` | 2 | `arch-check-index-nodes-rejected` |
| *(new)* node metadata violates the node schema: no block, no `package`, unknown key, scalar `claims`, the other variety's key | 2 | `arch-check-metadata-no-block`, `arch-check-metadata-missing-package`, `arch-check-metadata-unknown-key`, `arch-check-metadata-proto-key`, `arch-check-metadata-scalar-claims`, `arch-check-metadata-packages-on-precise`, `arch-check-metadata-package-on-virtual`, `arch-check-metadata-claims-on-virtual` |
| *(new)* malformed metadata: repeated key, second block, double-quoted value, unclosed array; metadata (even an empty block) on a nested element | 2 | `arch-check-metadata-repeated-key`, `arch-check-metadata-second-block`, `arch-check-metadata-double-quoted`, `arch-check-metadata-unclosed-array`, `arch-check-metadata-on-nested-element`, `arch-check-metadata-empty-on-nested-element` |
| claims-exist: package / claim missing on disk | 1 | `arch-check-claims-missing-package`, `arch-check-claims-missing-claim` |
| claims-exactly-once: claimed twice | 1 | `arch-check-claims-duplicate-claim` |
| claims-exactly-once: unclaimed top-level unit (non-units ignored) | 1 | `arch-check-claims-unclaimed-top-level` |
| claims-exactly-once: a model element's unit overlaps another node's declared unit (first in sorted order) | 1 | `arch-check-claims-child-collides`, `arch-check-model-descendant-collides` |
| claims-exist: a model element's unit missing on disk, at any depth | 1 | `arch-check-claims-child-missing`, `arch-check-claims-model-child-missing`, `arch-check-model-grandchild-missing` |
| claims-exist: virtual node containing elements (one finding; they map to no unit) | 1 | `arch-check-claims-virtual-children` |
| *(new)* model elements governed by convention with no `index.yaml` entry: child, grandchild, virtual kind nested under a precise node; multi-line metadata arrays | 0/1 | `arch-check-model-child-governed`, `arch-check-model-grandchild-governed`, `arch-check-model-virtual-kind-nested`, `arch-check-metadata-multiline-array` |
| *(new)* no model files: the declared language has no root element | 2 | `arch-check-identity-no-model-files` |
| arc42-exists: system doc / node doc / cross-cutting doc missing; orphan doc | 1 | `arch-check-arc42-system-missing`, `arch-check-arc42-node-doc-missing`, `arch-check-arc42-cross-cutting-missing`, `arch-check-arc42-orphan` |
| spec-mapping: mapped twice; node and cross-cutting; unknown touched node | 1 | `arch-check-spec-mapped-twice`, `arch-check-spec-node-and-cross-cutting`, `arch-check-spec-touches-unknown-node` |
| spec-mapping: unmapped dir; mapped dir missing; dir without spec.md; no openspec dir | 1 | `arch-check-spec-dir-unmapped`, `arch-check-spec-mapped-dir-missing`, `arch-check-spec-dir-without-spec-md`, `arch-check-spec-no-openspec-dir` |
| baseline-ratchet: missing (absent, not a mapping, no key) | 1 | `arch-check-ratchet-missing`, `arch-check-ratchet-not-mapping`, `arch-check-ratchet-no-baseline-key` |
| baseline-ratchet: not a non-negative integer, rendered with `!r` per value type | 1 | `arch-check-ratchet-bad-negative`, `arch-check-ratchet-bad-list`, `arch-check-ratchet-bad-string`, `arch-check-ratchet-bad-string-with-quote`, `arch-check-ratchet-bad-bool`, `arch-check-ratchet-bad-float`, `arch-check-ratchet-bad-null`, `arch-check-ratchet-bad-mapping` |
| baseline-ratchet: count differs | 1 | `arch-check-ratchet-mismatch` |
| model-truth: missing edge with witness; dead arrow; shadowed arrow; internal arrow | 1 | `arch-check-truth-missing-edge`, `arch-check-truth-dead-arrow`, `arch-check-truth-shadowed-arrow`, `arch-check-truth-internal-arrow` |
| model-truth measurement: witness order, TYPE_CHECKING forms, relative imports, root package, unmodelled modules, unclaimed sources | 0/1 | `arch-check-truth-witness-first-file`, `arch-check-truth-type-checking-excluded`, `arch-check-truth-type-checking-counted`, `arch-check-truth-type-checking-scopes`, `arch-check-truth-relative-imports`, `arch-check-truth-root-package-import`, `arch-check-truth-unmodelled-modules`, `arch-check-truth-unclaimed-source-skipped` |
| enforced-tags: unclosed tag; `[review]` with text; no colon; empty id; multi-line id | 1 | `arch-check-tags-unclosed`, `arch-check-tags-review-with-text`, `arch-check-tags-no-colon`, `arch-check-tags-empty-id`, `arch-check-tags-multiline-id` |
| enforced-tags: target id vs `issue_key_pattern` (default, custom, full match, quote repr) | 1 | `arch-check-tags-target-mismatch`, `arch-check-tags-target-quote`, `arch-check-tags-custom-issue-key-pattern`, `arch-check-tags-issue-key-full-match` |
| enforced-tags: unknown enforcement id (incl. the removed `model-identity`) | 1 | `arch-check-tags-unknown-id`, `arch-check-tags-tag-in-node-doc`, `arch-check-tags-model-identity-unknown` |
| enforced-tags: principle item without a status tag (continuations, nesting, headings) | 1 | `arch-check-tags-untagged-item`, `arch-check-tags-item-continuation` |
| diagrams-fresh: no diagrams block; block not a mapping | 1 | `arch-check-diagrams-block-absent`, `arch-check-diagrams-block-not-mapping` |
| diagrams-fresh: bad key, non-list, empty list, invalid ids (`!r`), duplicate ids | 1 | `arch-check-diagrams-entry-errors`, `arch-check-diagrams-bad-view-ids` |
| diagrams-fresh: mapped doc missing; view unknown | 1 | `arch-check-diagrams-doc-missing-and-view-unknown` |
| diagrams-fresh: marker pair missing / duplicate / out of order; orphan markers | 1 | `arch-check-diagrams-marker-missing`, `arch-check-diagrams-marker-duplicate`, `arch-check-diagrams-marker-order`, `arch-check-diagrams-orphan-markers` |
| diagrams-fresh: stale diagram (incl. CRLF bytes) | 1 | `arch-check-diagrams-stale`, `arch-check-diagrams-crlf-is-stale` |
| diagrams-fresh: every model-parse finding | 1 | `arch-check-parse-model-findings`, `arch-check-parse-spec-inline-before-brace` |
| diagrams-fresh: every views-parse finding; no `views {` block | 1 | `arch-check-parse-views-findings`, `arch-check-parse-views-no-views-block` |
| diagrams-fresh: `view_depth` not a mapping; unknown view; non-positive / non-integer values | 1 | `arch-check-view-depth-not-mapping`, `arch-check-view-depth-findings`, `arch-check-view-depth-bad-string`, `arch-check-view-depth-bad-bool`, `arch-check-view-depth-bad-float`, `arch-check-view-depth-bad-negative` |
| *(new)* `source_root`: src layout, prefix-free ids, architecture/specs stay at the repo root, `.`, symlink inside the repo | 0/1 | `arch-check-source-root-src-layout`, `arch-check-source-root-src-layout-findings`, `arch-check-source-root-control-findings`, `arch-check-source-root-architecture-stays-at-repo-root`, `arch-check-source-root-dot`, `arch-check-source-root-symlink-inside-repo` |
| *(new)* `source_root` invalid: absolute, `..`, escapes the repo, symlink escape, not a dir, missing, NUL, lacks `root_package`, not a string | 2 | `arch-check-source-root-invalid-absolute`, `arch-check-source-root-invalid-parent-segment`, `arch-check-source-root-invalid-escapes-repo`, `arch-check-source-root-invalid-symlink-escape`, `arch-check-source-root-invalid-not-a-directory`, `arch-check-source-root-invalid-missing`, `arch-check-source-root-invalid-lacks-root-package`, `arch-check-source-root-invalid-nul`, `arch-check-source-root-invalid-not-a-string` |
| *(new)* `root_package` invalid: absolute, `..`, empty or `.` segment, NUL, symlink escape or loop, outside `source_root`, not a dir | 2 | `arch-check-root-package-invalid-absolute`, `arch-check-root-package-invalid-parent-segment`, `arch-check-root-package-invalid-not-canonical`, `arch-check-root-package-invalid-nul`, `arch-check-root-package-invalid-symlink-escape`, `arch-check-root-package-invalid-symlink-loop`, `arch-check-root-package-invalid-outside-source-root`, `arch-check-root-package-invalid-not-a-directory` |
| *(new)* `index.yaml`: repo-owned `x-` keys are ignored | 0 | `arch-check-index-x-key-accepted` |
| *(new)* `index.yaml`: top-level `root_package` / `source_root`, unknown key (key named) | 2 | `arch-check-index-top-level-root-package-rejected`, `arch-check-index-top-level-source-root-rejected`, `arch-check-index-unknown-key-rejected` |
| *(new)* `index.yaml`: no language section (`x-` keys do not count) | 2 | `arch-check-index-no-language-section` |
| *(new)* root elements: undeclared top-level element, declared language without a root, metadata on a root | 2 | `arch-check-root-undeclared-top-level`, `arch-check-root-missing-declared-language`, `arch-check-root-metadata-on-root` |
| *(new)* root-relative relations: root-prefixed endpoint is unknown; relation outside every root is not recorded | 1 | `arch-check-relation-root-prefixed-endpoint`, `arch-check-relation-outside-root` |
| *(new)* views: unscoped; scoped to a node or an undeclared language | 1 | `arch-check-view-unscoped`, `arch-check-view-scope-not-a-root` |
| *(new)* qualified ids: unqualified `touches` names an unknown node (template audit in the case note) | 1 | `arch-check-qualified-ids-audit` |
| *(new)* single-language findings keep the pre-change order, with qualified ids | 1 | `arch-check-order-single-language` |
| *(new)* enforced-tags `[lang:]`: declared language; undeclared language; second or malformed tag; never a status tag | 0/1 | `arch-check-tags-lang-declared`, `arch-check-tags-lang-undeclared`, `arch-check-tags-lang-duplicate`, `arch-check-tags-lang-malformed`, `arch-check-tags-lang-not-a-status-tag` |
| *(new)* enforced-tags: a non-ASCII target id never matches | 1 | `arch-check-tags-target-non-ascii` |
| *(new)* top-level facts (`--top-level`): no model read, no units, edges between top-level units with the first witness | 0 | `arch-check-top-level-facts-python`, `arch-check-top-level-facts-typescript` |
| *(new)* top-level facts: an import inside one top-level unit yields no self-edge | 0 | `arch-check-top-level-facts-intra-unit`, `arch-check-top-level-facts-typescript` |
| *(new)* top-level facts: several modules of one unit importing another give one edge, witnessed by the first sorted source module | 0 | `arch-check-top-level-facts-one-witness` |
| *(new)* the arch-scaffold-python output passes the check; with an existing spec directory only the unmapped-spec finding remains | 0/1 | `arch-check-scaffolded-clean`, `arch-check-scaffolded-unmapped-spec` |

## la-arch-check: multi-language

| Branch | Exit | Cases |
|---|---|---|
| *(new)* disjoint roots, each arrow measured in its own language | 0 | `arch-check-mixed-disjoint-roots-clean` |
| *(new)* an arrow is covered only by its own language's edges (incl. same local ids under two roots) | 1 | `arch-check-mixed-arrow-dead-without-own-edge`, `arch-check-mixed-same-local-ids` |
| *(new)* witness: first sorted source module then target per language; missing edges sorted over the union | 1 | `arch-check-mixed-witness-order` |
| *(new)* claims findings in both languages, python first | 1 | `arch-check-mixed-claims-both-languages` |
| *(new)* fixed output order whatever the model's root order | 1 | `arch-check-mixed-output-order` |

## la-arch-check: TypeScript adapter

| Branch | Exit | Cases |
|---|---|---|
| *(new)* clean TS repo: directory, module-file and derived units, root barrel exempt, type-only import, no tsconfig | 0 | `arch-check-ts-ok` |
| *(new)* a unit is one module file of any source extension (`.ts .tsx .mts .cts .js .jsx .mjs .cjs`) | 0 | `arch-check-ts-unit-module-file` |
| *(new)* ambiguous unit (dir and file, or two extensions): declared and derived templates | 1 | `arch-check-ts-unit-ambiguous-declared`, `arch-check-ts-unit-ambiguous-derived` |
| *(new)* node in path notation; declared and derived units missing on disk | 1 | `arch-check-ts-units-missing` |
| *(new)* invisible files (test globs, `*.d.ts`, `node_modules`) are neither units nor measured sources | 1 | `arch-check-ts-invisible-files` |
| *(new)* top-level units (files, dirs with a visible source); dirs without sources and non-source files are not units | 1 | `arch-check-ts-unclaimed-top-level` |
| *(new)* derived unit collides with a declared unit, segment-wise | 1 | `arch-check-ts-claims-child-collides` |
| *(new)* symlinks followed inside `source_root`, not when escaping; a cycle is walked once | 1 | `arch-check-ts-symlinks` |
| *(new)* `source_root`: prefix-free units and module ids, nearest tsconfig searched from under it | 1 | `arch-check-ts-source-root` |
| *(new)* model-truth over TS edges: missing edge, dead arrow, shadowed arrow; legacy arrows counted by the ratchet | 1 | `arch-check-ts-truth-missing-edge`, `arch-check-ts-truth-dead-arrow`, `arch-check-ts-truth-shadowed-arrow`, `arch-check-ts-ratchet-mismatch` |
| *(new)* runtime edge forms: static import/export forms, `export * as ns`, `import x = require()`, mixed specifiers, empty named lists (`import {}`, `export {}`), value used as a type; literal `import()`/`require()` (also `.cjs`); non-literal and member calls ignored | 1 | `arch-check-ts-edges-static-forms`, `arch-check-ts-edges-dynamic-forms` |
| *(new)* type-only forms never count (`import type`, all-`type` specifiers, `export type`, `export type *`, `import type x = require()`, import types incl. `typeof` and nested, `/// <reference>`, JSDoc) | 0 | `arch-check-ts-edges-type-only` |
| *(new)* resolution: `paths`/`baseUrl`, bundler default, nodenext, node16 per-file format, `.js`/`.mjs` naming TS sources, index barrels | 1 | `arch-check-ts-resolve-paths-baseurl`, `arch-check-ts-resolve-bundler-default`, `arch-check-ts-resolve-nodenext`, `arch-check-ts-resolve-node16` |
| *(new)* tsconfig selection: section key, nearest upward, `extends` | 1 | `arch-check-ts-tsconfig-key`, `arch-check-ts-tsconfig-nearest`, `arch-check-ts-tsconfig-extends` |
| *(new)* a tsconfig holding JavaScript: setup error naming it, never executed | 2 | `arch-check-ts-tsconfig-never-executed` |
| *(new)* a tsconfig the compiler rejects (missing `extends` target): setup error naming it | 2 | `arch-check-ts-tsconfig-invalid` |
| *(new)* a `tsconfig` key resolving outside the repo: setup error naming `tsconfig` | 2 | `arch-check-ts-tsconfig-escapes` |
| *(new)* project references: solution root, nested, outDir/declarationDir/rootDir, `.d.mts`/`.d.cts` mapped to sources whether built or not, a stale output is the file it is; owner by depth-first order, overlapping includes, cycle, root fallback | 1 | `arch-check-ts-project-references`, `arch-check-ts-project-references-ownership` |
| *(new)* JS units and targets resolve with `allowJs` off | 1 | `arch-check-ts-allowjs-off` |
| *(new)* externals (npm package, `node:` and bare builtins, subpath, unresolved bare), targets outside `root_package`, root barrel target | 0 | `arch-check-ts-externals` |
| *(new)* unresolved relative specifiers attributed lexically (`..`, `?`/`#` suffix, extension), escape unattributed | 1 | `arch-check-ts-unresolved-relative` |
| *(new)* native TS facts (`--language typescript --emit facts`): units in model order (present, missing, ambiguous with sorted candidates), sorted top-level units, sorted edges with first witnesses | 0 | `arch-check-ts-facts` |

## la-arch-diagrams

| Branch | Exit | Cases |
|---|---|---|
| fresh docs: nothing printed, nothing written | 0 | `arch-diagrams-noop-when-fresh` |
| rewritten docs printed; rendering (nested, flat, predicates, several views and docs, title escape, virtual shape, legacy dashing) | 0 | `arch-diagrams-rewrite-hierarchical`, `arch-diagrams-rewrite-flat-depth-1`, `arch-diagrams-root-flag`, `arch-diagrams-predicates-and-multiple-views`, `arch-diagrams-title-escape-and-virtual-shape`, `arch-diagrams-legacy-only-when-all-contributors-are`, `arch-diagrams-crlf-outside-block-preserved` |
| index missing / invalid YAML / not a mapping / no diagrams block / block not a mapping | 1 | `arch-diagrams-index-missing`, `arch-diagrams-index-invalid-yaml`, `arch-diagrams-index-not-mapping`, `arch-diagrams-no-diagrams-block`, `arch-diagrams-diagrams-not-mapping` |
| model/views findings block generation (incl. *(new)* malformed metadata) | 1 | `arch-diagrams-parse-findings-block-generation`, `arch-diagrams-malformed-metadata` |
| key not an arc42 path (`!r`) | 1 | `arch-diagrams-key-not-arc42-path` |
| view not defined (incl. no views.c4, string view list) | 1 | `arch-diagrams-view-not-defined`, `arch-diagrams-no-views-file`, `arch-diagrams-view-ids-string-iterates` |
| missing / duplicate / out-of-order markers; earlier docs already written | 1 | `arch-diagrams-marker-missing`, `arch-diagrams-marker-duplicate`, `arch-diagrams-marker-order`, `arch-diagrams-first-error-stops-later-docs` |
| mapped doc missing or a directory (OSError) | 1 | `arch-diagrams-doc-missing`, `arch-diagrams-doc-is-directory` |
| usage error; `--help` | 2/0 | `arch-diagrams-usage-unknown-flag`, `arch-diagrams-help` |
| *(new)* a wrapped model renders as unwrapped: grandchild subgraphs, nested predicate endpoints, legacy roll-up, `view_depth` | 0 | `arch-diagrams-wrapped-nested-predicates-depth` |
| *(new)* same local ids under two roots: one relation per root, each scoped view draws its own | 0 | `arch-diagrams-same-local-ids-two-roots` |
| *(new)* an unscoped view blocks generation | 1 | `arch-diagrams-view-unscoped-refuses` |

## la-arch-scaffold

| Branch | Exit | Cases |
|---|---|---|
| *(new)* kinds and tags in `model/specification.c4`, one node per top-level unit and one relation per measured edge in `model/<language>.c4`, views, arc42 with diagrams, index additions; written paths in fixed order | 0 | `arch-scaffold-python` |
| *(new)* cycle keeps both arrows; an index already setting `legacy_arrows` gets only `diagrams`, the rest byte-identical | 0 | `arch-scaffold-cycle` |
| *(new)* a unit without edges still gets a node | 0 | `arch-scaffold-unit-without-edges` |
| *(new)* mixed repo: one shared `specification.c4`, one model file and one view per language, both diagrams in `system.arc42.md` | 0 | `arch-scaffold-mixed`, `twin-scaffold-forwarded-top-level` |
| *(new)* id derivation: hyphen to `_` with the raw title; leading digit gets `n_`; order follows unit names | 0 | `arch-scaffold-ts-hyphenated`, `arch-scaffold-leading-digit` |
| *(new)* id collision between two units of one language: names both, writes nothing | 2 | `arch-scaffold-id-collision` |
| *(new)* an existing `model/*.c4`, `views.c4` or `*.arc42.md` refused by name, repo unchanged | 2 | `arch-scaffold-existing-model`, `arch-scaffold-existing-views`, `arch-scaffold-existing-arc42` |
| *(new)* `architecture/index.yaml` missing or not valid YAML, nothing written | 2 | `arch-scaffold-index-missing`, `arch-scaffold-index-invalid` |
| *(new)* other twin unreachable: install hint, nothing written | 2 | `arch-scaffold-twin-unavailable` |
| *(new)* other twin returns schema-invalid top-level facts: protocol failure, nothing written | 2 | `twin-scaffold-top-level-schema-invalid` |

## la-config

| Branch | Exit | Cases |
|---|---|---|
| `show`: defaults (no file, empty, comments, `{}`), partial, falsy kept, YAML 1.1, duplicate keys, full, integer float, non-ASCII, portable pattern | 0 | `config-show-defaults`, `config-show-empty-file`, `config-show-empty-mapping`, `config-show-comments-only`, `config-show-partial-nested`, `config-show-explicit-falsy`, `config-show-yaml11-booleans`, `config-show-duplicate-key`, `config-show-full`, `config-show-integer-ratio`, `config-show-non-ascii`, `config-show-portable-patterns` |
| *(new)* `commands.typecheck`: per-language defaults (shown in every `show` golden), explicit `null` kept, `get` of a default | 0 | `config-show-typecheck-null`, `config-get-typecheck-default` |
| *(new)* `commands.typecheck` as a plain string, or with an unknown language key | 1 | `config-error-typecheck-string`, `config-error-typecheck-unknown-language` |
| *(new)* gate keys: `tracker`, `openspec`, `architecture`, `reviewers.codex`, `conventions.rules` with their defaults (shown in every `show` golden), explicit values and falsy values kept, YAML 1.1 `codex: no`, `get` of the rules default | 0 | `config-show-defaults`, `config-show-full`, `config-show-explicit-falsy`, `config-show-yaml11-booleans`, `config-get-conventions-rules-default` |
| *(new)* removed keys `reviewers.coderabbit` and `reviewers.sonar.enabled`; unknown `tracker`; unknown `conventions.rules` id | 1 | `config-error-removed-coderabbit`, `config-error-removed-sonar-enabled`, `config-error-unknown-tracker`, `config-error-unknown-conventions-rule` |
| *(new)* strict scalar types: string/int for a bool, string for a number (pydantic used to coerce) | 1 | `config-error-lax-string-bool`, `config-error-lax-int-bool`, `config-error-lax-string-float` |
| `get`: bool, null (empty line), string, float, list/mapping as JSON, non-ASCII | 0 | `config-get-bool-true`, `config-get-bool-false`, `config-get-null-is-empty`, `config-get-string`, `config-get-float`, `config-get-integer-float`, `config-get-empty-list`, `config-get-list`, `config-get-mapping`, `config-get-non-ascii`, `config-get-non-ascii-in-list` |
| `get`: unknown key; key into a scalar; an object member name | 2 | `config-get-unknown-key`, `config-get-into-scalar`, `config-get-object-member` |
| invalid config (key named) | 1 | `config-error-unknown-top-key`, `config-error-unknown-nested-key`, `config-error-ratio-zero`, `config-error-ratio-above-one`, `config-error-ratio-negative`, `config-error-invalid-regex`, `config-error-pattern-not-string`, `config-error-bool-not-bool`, `config-error-exempt-not-list`, `config-error-command-not-string`, `config-error-null-section`, `config-error-top-level-list`, `config-error-top-level-scalar`, `config-error-invalid-yaml`, `config-get-invalid-config` |
| *(new)* non-portable `issue_key_pattern` | 1 | `config-error-non-portable-lookbehind`, `config-error-non-portable-named-group`, `config-error-non-portable-inline-flag`, `config-error-non-portable-possessive`, `config-error-non-portable-atomic` |
| repo root: `--root`, discovery from a subdir, no `.git` | 0 | `config-root-flag`, `config-root-discovery-from-subdir`, `config-root-without-git-is-cwd` |
| usage errors; `--help`; *(new)* `--` honoured | 2/0 | `config-usage-no-args`, `config-usage-unknown-subcommand`, `config-usage-get-without-key`, `config-usage-root-after-subcommand`, `config-usage-unknown-flag`, `config-usage-show-extra-positional`, `config-help`, `config-double-dash` |

## la-doctor

| Branch | Exit | Cases |
|---|---|---|
| healthy (defaults / config file / `--root`), `--expect` matching; no config file means no consistency checks | 0 | `doctor-ok-defaults`, `doctor-ok-config-file`, `doctor-root-flag`, `doctor-expect-match` |
| version mismatch; invalid config; `git`/`gh` missing; all problems in order | 1 | `doctor-expect-mismatch`, `doctor-config-invalid`, `doctor-missing-git`, `doctor-missing-gh`, `doctor-missing-both`, `doctor-all-problems-in-order` |
| usage errors; `--help` | 2/0 | `doctor-usage-unknown-flag`, `doctor-usage-expect-without-value`, `doctor-help` |
| *(new)* `--twin` (internal option) prints `<language> <version> <contract-hash>`, per twin | 0 | `doctor-twin-identity-python`, `doctor-twin-identity-typescript` |
| *(new)* `--require-config`: missing file is a finding naming `/la:init`; a valid, consistent file is healthy; an invalid file reports the config error | 1/0/1 | `doctor-require-config-missing`, `doctor-require-config-present`, `doctor-require-config-invalid` |
| *(new)* config vs disk: `openspec` true without / false with `openspec/`; `architecture` true without / false with `architecture/index.yaml`; `tracker: none` with `openspec: false`; several findings in a fixed order | 1 | `doctor-openspec-enabled-absent`, `doctor-openspec-disabled-present`, `doctor-architecture-enabled-absent`, `doctor-architecture-disabled-present`, `doctor-no-plan-store`, `doctor-several-inconsistencies` |
| *(new)* an `architecture/` directory without `index.yaml` is not a setup | 0 | `doctor-architecture-unrelated-dir` |

`--contract-hash` *(new)* prints a value that changes with `shared/`; it is pinned by `tests/test_contract.py`.

## la-check-conventions

| Branch | Exit | Cases |
|---|---|---|
| gate CLEAR | 0 | `conventions-clean`, `conventions-import-wrappers-in-prologue`, `conventions-missing-file-skipped`, `conventions-text-ratio-empty-file`, `conventions-text-ratio-boundary-equal`, `conventions-test-file-classification-bare-names` |
| import-not-top: after code, in functions, wrappers after code, def in a wrapper, second string | 1 | `conventions-import-after-code`, `conventions-import-in-functions`, `conventions-import-wrappers-after-code`, `conventions-import-wrapper-with-def-ends-prologue`, `conventions-import-after-second-string` |
| composite-assert (tests only); raises-single-throw (every callee form) | 1 | `conventions-composite-assert`, `conventions-raises-single-throw` |
| test-file classification | 1/0 | `conventions-test-file-classification`, `conventions-test-file-classification-bare-names` |
| waivers (valid, compact, wrong rule, no reason, wrong case) | 1 | `conventions-waivers` |
| unreadable (decode error, directory); syntax error | 1 | `conventions-unreadable-binary`, `conventions-unreadable-directory`, `conventions-syntax-error` |
| text-ratio: source over, tests over, standalone strings; cap from flag / config | 1/0 | `conventions-text-ratio-source-over`, `conventions-text-ratio-tests-over`, `conventions-text-ratio-standalone-strings`, `conventions-text-ratio-cap-flag`, `conventions-text-ratio-config-cap` |
| exempt globs (config + `--exclude`, fnmatch semantics) | 0 | `conventions-exempt-config-and-flag`, `conventions-accepted-invocation-vector`, `conventions-accepted-invocation-vector-with-exempt-file`, `conventions-equals-forms` |
| `--base`: committed, staged, unstaged, untracked, deleted, renamed; origin vs local; *(new)* empty change set labelled `source` | 0/1 | `conventions-base-committed`, `conventions-base-working-tree`, `conventions-base-uses-origin-not-local`, `conventions-base-no-python-changes` |
| `--base` ref missing; not a git repo | 2 | `conventions-base-ref-missing`, `conventions-base-not-a-git-repo` |
| PR lookup: resolves, `--repo`, fails; `--base` wins; `--file` wins | 1/2/0 | `conventions-pr-resolves-base`, `conventions-pr-with-repo`, `conventions-pr-lookup-fails`, `conventions-pr-and-base-prefers-base`, `conventions-file-overrides-base`, `conventions-double-dash-pr` |
| invalid config | 2 | `conventions-config-invalid` |
| usage errors; `--help`; *(new)* abbreviated option rejected | 2/0 | `conventions-usage-no-target`, `conventions-usage-cap-not-a-number`, `conventions-help`, `conventions-usage-abbreviated-option` |
| *(new)* an explicit path with an unknown extension skipped with one warning, not counted (incl. `test_x.txt`, `x_test.pyc`, `test_` in the classification case) | 0/1 | `conventions-file-unknown-extension`, `conventions-test-file-classification` |
| *(new)* NUL-safe `--base` diff: spaces, non-ASCII and a leading dash keep their real names | 1 | `conventions-base-nul-safe-paths` |
| *(new)* language facts emitted natively (`--language L --emit facts`, paths on stdin): ok with detections and line text, missing, unreadable, syntax-error | 0 | `conventions-facts-emit-python`, `conventions-facts-emit-typescript` |
| *(new)* facts request whose stdin is not a JSON array of paths | 2 | `conventions-facts-stdin-invalid` |
| *(new)* `conventions.rules`: only configured rules report; an unconfigured text-ratio prints no ratio line; test-only rules dropped; `[]` keeps only the summary and CLEAR; a waiver for an unconfigured rule does nothing | 1/0 | `conventions-rules-one-rule-dropped`, `conventions-rules-test-only-dropped`, `conventions-rules-gate-off`, `conventions-rules-waiver-unconfigured` |
| *(new)* `conventions.rules`: unreadable/syntax-error reported iff a configured rule applies to the file | 0/1 | `conventions-rules-file-errors-gate-off`, `conventions-rules-syntax-error-rule-on`, `conventions-rules-file-error-test-only-rules` |
| *(new)* a conventions section without `rules` keeps every registry rule | 1 | `conventions-rules-default` |

## la-check-conventions: multi-language

| Branch | Exit | Cases |
|---|---|---|
| *(new)* one report: path order across languages, ratio groups spanning both, `.py and TS/JS` label, mixed RED waiver line | 1 | `conventions-mixed-one-verdict` |
| *(new)* `--base` routes each file by extension; other files silently ignored; deletions excluded | 1 | `conventions-mixed-base-diff` |
| *(new)* a rename across languages is checked under the new path by the new language | 1 | `conventions-mixed-rename-across-languages` |
| *(new)* the invoking twin filters both languages' facts by `conventions.rules` | 1 | `conventions-rules-mixed` |

## la-check-conventions: TypeScript adapter

| Branch | Exit | Cases |
|---|---|---|
| *(new)* clean TS source and test files: CLEAR with the TS/JS label | 0 | `conventions-ts-clean` |
| *(new)* import-not-top: late static import, `import type`, `import x = require()`, `export … from` before an import; directive prologue; a string after an import; a top-level `require()` ends the prologue | 1 | `conventions-ts-import-after-code`, `conventions-ts-import-directive-prologue`, `conventions-ts-import-require-ends-prologue` |
| *(new)* `require()` outside module scope by the n/global-require ancestor allow-list | 1 | `conventions-ts-require-not-top` |
| *(new)* never flagged: dynamic `import()`, type-position `import('x')`, `declare module` and namespace bodies, a bottom barrel `export … from` | 0 | `conventions-ts-import-allowed-forms` |
| *(new)* composite-assert (`expect`, `assert`, `assert.ok`, parenthesized `&&`; not `||`, not outside tests) | 1 | `conventions-ts-composite-assert` |
| *(new)* raises-single-throw: each `toThrow*` matcher, `.rejects`, `assert.throws`/`rejects`, `new` counted, multi-line; one call and `.not.toThrow` clean | 1 | `conventions-ts-raises-single-throw` |
| *(new)* `// ALLOW(<rule>): <reason>` waivers per rule incl. a multi-line construct; wrong rule, no reason, lowercase, `#` form, later line do not waive | 1 | `conventions-ts-waivers` |
| *(new)* syntax error (first parse diagnostic), excluded from text-ratio; invalid UTF-8 unreadable | 1 | `conventions-ts-syntax-error`, `conventions-ts-unreadable-invalid-utf8` |
| *(new)* every ScriptKind: `.js .jsx .mjs .cjs .tsx .mts .cts` | 1 | `conventions-ts-script-kinds` |
| *(new)* TS test globs decide where tests-only rules apply | 1 | `conventions-ts-test-file-classification` |
| *(new)* text-ratio at and just over the cap, per group | 0/1 | `conventions-ts-text-ratio-source-at-cap`, `conventions-ts-text-ratio-source-over`, `conventions-ts-text-ratio-tests-at-cap`, `conventions-ts-text-ratio-tests-over` |
| *(new)* text-only lines (block comments beside code, trailing comments and JSDoc, blank lines inside a block, comment-like strings); BOM, CRLF, lone CR, no final newline | 1 | `conventions-ts-text-lines`, `conventions-ts-line-breaks` |
| *(new)* `--base` diff of TS files: committed, staged, unstaged, renamed, non-ASCII; untracked and deleted not checked | 1 | `conventions-ts-base-diff` |
| *(new)* `conventions.rules` on TS/JS files: one rule dropped, test-only rules dropped, `expect(a && b)` with only text-ratio, `[]`, unconfigured-rule waiver, default | 1/0 | `conventions-rules-ts-one-rule-dropped`, `conventions-rules-ts-test-only-dropped`, `conventions-rules-ts-test-file`, `conventions-rules-ts-gate-off`, `conventions-rules-ts-waiver-unconfigured`, `conventions-rules-ts-default` |
| *(new)* `conventions.rules` on TS/JS file errors: none reported with `[]`, syntax-error reported with text-ratio | 0/1 | `conventions-rules-ts-file-errors-gate-off`, `conventions-rules-ts-syntax-error-rule-on` |

## la-count-comments

| Branch | Exit | Cases |
|---|---|---|
| per-file counts and total (comments, every docstring owner) | 0 | `count-comments-files` |
| missing file, syntax error, tokenize error | 0 | `count-comments-missing-file`, `count-comments-syntax-error`, `count-comments-tokenize-error` |
| passthrough argv (`--`, `--help` are paths); *(new)* both skipped with the unknown-extension warning | 0 | `count-comments-double-dash-is-a-path`, `count-comments-help-is-a-path` |
| *(new)* unknown extension skipped with one warning | 0 | `count-comments-unknown-extension` |
| *(new)* TS: JSDoc as doc, other comments incl. trailing and `/**/`, distinct lines, shebang neither, BOM+CRLF, missing file; syntax error still counted; `--range` | 0 | `count-comments-ts-files`, `count-comments-ts-syntax-error`, `count-comments-ts-range` |
| *(new)* multi-language: files in argument order across languages; `--range` | 0 | `count-comments-mixed-files`, `count-comments-mixed-range` |
| `--range`: added, removed, unchanged, new file; repo-relative ref paths | 0 | `count-comments-range`, `count-comments-range-paths-are-repo-relative` |
| usage: no args; `--range` with too few args | 2 | `count-comments-usage-no-args`, `count-comments-range-too-few-args` |

## la-typecheck

| Branch | Exit | Cases |
|---|---|---|
| *(new)* applicability: stray JS in a Python repo, explicit entry without markers, `null` off, exempt and git-ignored files not counted, nothing to check | 0 | `typecheck-python-stray-js`, `typecheck-python-explicit-without-markers`, `typecheck-ts-language-off`, `typecheck-ts-exempt-and-ignored-not-counted`, `typecheck-no-languages` |
| *(new)* not a git repo; checker not found (first word named); `commands.typecheck` as a string | 2 | `typecheck-not-a-git-repo`, `typecheck-ts-not-found`, `typecheck-python-not-found`, `typecheck-config-string-rejected` |
| *(new)* configured command that does not split into shell words | 2 | `typecheck-python-command-unsplittable` |
| *(new)* usage error; `--help` | 2/0 | `typecheck-usage-unknown-option`, `typecheck-help` |
| *(new)* Python passthrough: clean (local bin preferred), new errors, shrink, write with errors, exit >= 2, a non-basedpyright command in write mode | 0/1/2 | `typecheck-python-clean`, `typecheck-python-new-errors`, `typecheck-python-shrink`, `typecheck-python-write-with-errors`, `typecheck-python-checker-crash`, `typecheck-python-custom-command-write` |
| *(new)* TS ratchet: unchanged (local bin preferred), from a subdirectory, line shift | 0 | `typecheck-ts-unchanged`, `typecheck-ts-from-subdirectory`, `typecheck-ts-line-shift` |
| *(new)* TS new errors: new key with continuation lines, count increase listing every occurrence, new + resolved without shrink | 1 | `typecheck-ts-new-error`, `typecheck-ts-count-increase`, `typecheck-ts-new-and-resolved` |
| *(new)* TS baseline shrinks; written fresh (sorted), clean (empty), path with spaces and parentheses, continuation lines, diagnostics on stderr, absolute path keyed relative | 0 | `typecheck-ts-shrink`, `typecheck-ts-write-fresh`, `typecheck-ts-write-clean`, `typecheck-ts-path-spaces-parens`, `typecheck-ts-continuation-lines`, `typecheck-ts-diagnostics-on-stderr`, `typecheck-ts-absolute-path` |
| *(new)* TS failures: every baseline exists in write mode, global diagnostic, non-zero exit with nothing parsed, malformed or wrongly shaped baseline | 2 | `typecheck-ts-write-all-exist`, `typecheck-ts-global-diagnostic`, `typecheck-ts-nonzero-nothing-parsed`, `typecheck-ts-malformed-baseline`, `typecheck-ts-baseline-wrong-shape` |
| *(new)* multi-language: Python first, exit max; write for a newly added language skips the existing baseline | 1/0 | `typecheck-mixed-order-exit-max`, `typecheck-mixed-write-new-language` |

## dr-compliance

| Branch | Exit | Cases |
|---|---|---|
| every check, string-sorted output | 1 | `compliance-all-checks` |
| `--select` subset / whitespace / empty; unknown check | 1/0/2 | `compliance-select-subset`, `compliance-select-whitespace`, `compliance-select-empty`, `compliance-select-unknown` |
| `--attr` blind spots | 1 | `compliance-attr-blindspot` |
| directory recursion; parse error; clean | 1/0 | `compliance-directory-recursion`, `compliance-parse-error`, `compliance-clean` |
| `--` before paths | 0/1 | `compliance-double-dash`, `compliance-double-dash-dash-path` |
| usage error; `--help` | 2/0 | `compliance-usage-no-paths`, `compliance-help` |

## dr-mock-lint

| Branch | Exit | Cases |
|---|---|---|
| every mock and patch form | 1 | `mock-lint-violations` |
| directory recursion; clean | 1/0 | `mock-lint-directory-recursion`, `mock-lint-clean` |
| usage error | 2 | `mock-lint-usage-no-args` |

## dr-refactor

| Branch | Exit | Cases |
|---|---|---|
| rename: dry-run / apply by name, line+col, offset; hierarchy on/off; `--unsure include` warning; *(new)* changes printed sorted by path | 0 | `refactor-rename-dry-run`, `refactor-rename-apply`, `refactor-rename-single-file-dry-run`, `refactor-rename-single-file-apply`, `refactor-rename-line-col`, `refactor-rename-no-in-hierarchy`, `refactor-rename-offset`, `refactor-rename-unsure-include` |
| move-symbol (*(new)* sorted by path); move-module (tracked, untracked); `--project` | 0 | `refactor-move-symbol-apply`, `refactor-move-module-apply`, `refactor-move-module-uncommitted`, `refactor-project-flag` |
| no locator; line out of range; symbol not found; path outside the project | 1 | `refactor-no-locator`, `refactor-line-out-of-range`, `refactor-symbol-not-found`, `refactor-path-outside-project` |
| usage errors; `--help` | 2/0 | `refactor-usage-no-subcommand`, `refactor-usage-rename-without-new-name`, `refactor-usage-rename-without-file`, `refactor-usage-bad-unsure-choice`, `refactor-usage-offset-not-int`, `refactor-help` |

## Review shims and their bundled scripts

| Branch | Exit | Cases |
|---|---|---|
| review shims ignore the config (no config, invalid config) | 0 | `shim-fetch-coderabbit-threads-disabled`, `shim-reply-invalid-coderabbit-disabled`, `shim-fetch-coderabbit-threads-config-invalid`, `shim-reply-invalid-coderabbit-config-invalid`, `shim-reply-to-pr-thread-ignores-config`, `shim-fetch-failed-pr-checks-ignores-config`, `shim-wait-for-reviews-ignores-config` |
| fetch-coderabbit-threads: threads + nitpicks + outside-diff; all authors; argument and repo errors | 0/2 | `shim-fetch-coderabbit-threads-ok`, `shim-fetch-coderabbit-threads-all-authors`, `shim-fetch-coderabbit-threads-bad-pr`, `shim-fetch-coderabbit-threads-bad-repo`, `shim-fetch-coderabbit-threads-unknown-flag`, `shim-fetch-coderabbit-threads-repo-autodetect-fails` |
| reply-invalid-coderabbit: mention prepended; empty body | 0/2 | `shim-reply-invalid-coderabbit-ok`, `shim-reply-invalid-coderabbit-empty-body` |
| reply-to-pr-thread: URL; explicit ids; review-summary URL; bad URL; empty body; bad id | 0/2 | `shim-reply-to-pr-thread-ok`, `shim-reply-to-pr-thread-explicit-ids`, `shim-reply-to-pr-thread-review-summary-url`, `shim-reply-to-pr-thread-bad-url`, `shim-reply-to-pr-thread-empty-body`, `shim-reply-to-pr-thread-bad-comment-id` |
| fetch-failed-pr-checks: failures with logs; full-log fallback; none; argument errors | 0/2 | `shim-fetch-failed-pr-checks-ok`, `shim-fetch-failed-pr-checks-full-log-fallback`, `shim-fetch-failed-pr-checks-none`, `shim-fetch-failed-pr-checks-bad-pr`, `shim-fetch-failed-pr-checks-bad-max-log` |
| wait-for-reviews: CodeRabbit absent (no check, no comment); fresh summary; rate limited; gate fails closed; no PR; repo auto-detect fails | 0/3/1/64/2 | `shim-wait-for-reviews-coderabbit-absent`, `shim-wait-for-reviews-fresh-summary`, `shim-wait-for-reviews-rate-limited`, `shim-wait-for-reviews-gate-fails-closed`, `shim-wait-for-reviews-requires-pr`, `shim-wait-for-reviews-repo-autodetect-fails` |
| *(new)* wait-for-reviews: CodeRabbit present by comment only runs the settle; `--skip-coderabbit` is an unknown flag | 0/64 | `shim-wait-for-reviews-coderabbit-by-comment`, `shim-wait-for-reviews-skip-coderabbit-rejected` |
| *(new)* pr-reviewers: CodeRabbit by status check / by comment; no bots | 0 | `shim-pr-reviewers-coderabbit-by-status`, `shim-pr-reviewers-coderabbit-by-comment`, `shim-pr-reviewers-no-bots` |
| *(new)* pr-reviewers: Sonar check (run or status context, case-insensitive); key from config, properties file, check URL, none | 0 | `shim-pr-reviewers-sonar-key-from-config`, `shim-pr-reviewers-sonar-key-from-properties`, `shim-pr-reviewers-sonar-key-from-url`, `shim-pr-reviewers-sonar-status-context`, `shim-pr-reviewers-sonar-without-key` |
| *(new)* pr-reviewers: gh failure relayed, no JSON; missing or non-numeric PR | 2 | `shim-pr-reviewers-gh-fails`, `shim-pr-reviewers-requires-pr`, `shim-pr-reviewers-bad-pr` |

The scripts are shared byte-for-byte between the twins. Their remaining internal branches (thread and
comment pagination, the polling loops' sleep-and-retry paths, the 10-minute CodeRabbit cap) depend on wall
time or many paged responses. Those branches are pinned by `tests/test_review_scripts.py`, not by the corpus.

## Twin forwarding

| Branch | Exit | Cases |
|---|---|---|
| *(new)* other twin found by identity: a mismatching twin earlier on PATH is probed and skipped; `<repo>/node_modules/.bin` when no PATH dir qualifies | 0 | `twin-shadowed-twin-found`, `twin-found-in-node-modules-bin` |
| *(new)* discovery skips a PATH dir whose real path was already probed, a dir without `la-doctor` and a non-executable `la-doctor`; the first qualifying dir serves | 0 | `twin-discovery-dedup-and-skip` |
| *(new)* version / contract mismatch skipped, runner probed (`uvx --from …==<version>`, `npx -y -p …@<version>`), command run through it, exit and streams passed through | 1/0 | `twin-version-mismatch-runner-probed`, `twin-contract-mismatch-runner-probed` |
| *(new)* twin unavailable (install hint): no twin and no runner; runner probe fails; runner probe reports another identity | 2 | `twin-unavailable-typescript`, `twin-unavailable-python`, `twin-runner-probe-fails`, `twin-runner-probe-wrong-identity` |
| *(new)* npm twin forwards each Python-only command wholesale; output equals the PyPI twin's own run | 0/1 | `twin-forward-refactor`, `twin-forward-compliance`, `twin-forward-mock-lint` |
| *(new)* conventions commands through the npm twin on Python files: Python facts from the PyPI twin, output equals its own run | 0 | `twin-conventions-python-files-from-npm-twin`, `twin-count-comments-python-files-from-npm-twin` |
| *(new)* conventions facts folded into one report (carried-text waiver, tests-only filter, stdin path list); comment counts from facts | 1/0 | `twin-conventions-facts-folded`, `twin-conventions-facts-folded-from-python`, `twin-count-comments-facts-folded` |
| *(new)* conventions facts protocol failure: malformed, schema-invalid, wrong version, killed by a signal; non-zero exit relayed | 2 | `twin-conventions-facts-malformed`, `twin-conventions-facts-schema-invalid`, `twin-conventions-facts-wrong-version`, `twin-conventions-facts-killed-by-signal`, `twin-conventions-facts-nonzero-exit-relayed` |
| *(new)* conventions facts: twin unreachable for a mixed diff; request for a non-owned language; `LA_FORWARDED=1` refusal | 2 | `twin-conventions-facts-unavailable`, `twin-conventions-facts-non-native-typescript`, `twin-conventions-facts-non-native-python`, `twin-conventions-facts-refused-when-forwarded` |
| *(new)* conventions commands on own-language files never probe the other twin | 0 | `twin-conventions-own-language-typescript`, `twin-conventions-own-language-python`, `twin-count-comments-own-language-typescript` |
| *(new)* `la-typecheck`: the other language runs through its twin (`--language L`, streams relayed, exit max); `--language` for a non-owned language refused without a process; twin unreachable | 1/2 | `twin-typecheck-forwarded-typescript`, `twin-typecheck-non-native-typescript`, `twin-typecheck-non-native-python`, `twin-typecheck-unavailable` |
| *(new)* neutral commands never forward (other twin unreachable) | 0 | `twin-neutral-config-show`, `twin-neutral-doctor`, `twin-neutral-arch-diagrams` |
| *(new)* own-language inputs never probe or run the other twin | 0 | `twin-own-language-python`, `twin-own-language-typescript` |
| *(new)* facts emitted natively (Python): unit statuses in model order, sorted top-level units, sorted edges with first witness | 0 | `twin-facts-emit-python` |
| *(new)* facts request for a non-owned language, no process started | 2 | `twin-facts-non-native-typescript`, `twin-facts-non-native-python` |
| *(new)* foreign facts folded into one report (per-language claims incl. ambiguity, union model-truth) | 1 | `twin-facts-folded` |
| *(new)* facts run exits non-zero: its stderr relayed verbatim | 2 | `twin-facts-setup-error-relayed`, `twin-facts-nonzero-exit-relayed` |
| *(new)* facts protocol failure: malformed, truncated, missing, schema-invalid, wrong language / version / contract hash, killed by a signal; from either twin | 2 | `twin-facts-malformed-json`, `twin-facts-truncated-json`, `twin-facts-missing-document`, `twin-facts-schema-invalid`, `twin-facts-wrong-language`, `twin-facts-wrong-version`, `twin-facts-wrong-contract-hash`, `twin-facts-killed-by-signal`, `twin-facts-malformed-json-from-python` |
| *(new)* `LA_FORWARDED=1`: forwarding refused without probing (wholesale command, facts request) | 2 | `twin-forward-refused-wholesale`, `twin-forward-refused-facts` |
| *(new)* the npm twin refuses a Python top-level facts request without starting any process | 2 | `twin-facts-top-level-non-native-python` |
| *(new)* `la-arch-scaffold` through the PyPI twin gets TypeScript top-level facts from the npm twin | 0 | `twin-scaffold-forwarded-top-level` |
| *(new)* schema-invalid top-level facts from the npm twin: protocol failure | 2 | `twin-scaffold-top-level-schema-invalid` |

## Excluded: crashes

These inputs crash today's tool with a traceback (exit 1). A traceback's module paths and line numbers cannot
survive the restructure, so the corpus does not pin them, and the post-change behaviour is not part of the
contract:

- `la-arch-check`: a syntax error in a measured `.py` file
- `la-arch-diagrams`: a `diagrams` entry whose view list is neither a list nor a string
- `dr-compliance`, `dr-mock-lint`: a path that does not exist; `dr-mock-lint` on a file with a syntax error
- `dr-refactor`: rope errors on a location that is not a renameable symbol

## Excluded from byte comparison

- `--help` text and parser error wording: the exit code is pinned and the streams are `ignore`.
- Config validation wording: the exit code and the offending key are pinned (`contains`).
- Wording from git and the YAML parser.
