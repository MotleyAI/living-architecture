## Context

See proposal.md (Why). The PyPI twin is decomposed into `contract`, `config`, `cli`, `c4`, `archcheck`, `lang`,
`conventions`, `review`, `doctor` and `refactor` (DEV-1990 D8). Nodes are declared in LikeC4 metadata on top-level
elements (DEV-2030). `c4` rejects relations inside any element body (`c4.relation-in-body`), and the view grammar
counts levels from the model's top. The conformance runner (`python/tests/test_conformance.py`) uses one
`language` per case for overlay, applicability and golden suffix. Normative harnesses
(`architecture/system.arc42.md`): principle 1 (twins identical; the corpus decides), 2 (parameters, texts and
command surfaces only from `shared/`), 3 (language-specific code only in `lang` and `refactor`), 4 (no target-repo
code is imported or executed). This change satisfies all four; no principle wording changes, only a second
`[enforced: test:…]` tag on principle 1 (approval-gated, task 10).

## Goals / Non-Goals

**Goals:**
- Output is a function of the repo alone, never of which twin was invoked.
- Language-specific facts come from exactly one adapter per language; all arch-check math has one implementation
  per twin.
- A migrated single-language repo's diagrams do not change.

**Non-Goals:**
- Cross-root relations and cross-language views (DEV-2029).
- TS conventions, comment counting, `la-typecheck` (DEV-2026); TS `dr-*` and the first public npm release
  (DEV-2027).
- Multi-package repos (one root per language).
- A migration command.
- A `language:` config key or marker-file auto-detection (dropped from the issue: index sections and file
  extensions already say which language applies, and a single repo language cannot route a mixed diff).

## Decisions

### D1 — Language roots
Each `index.yaml` language section has a model root element of the same id; nodes are its children. Alternatives:
per-language suffixed metadata keys on shared nodes (`package_typescript`), rejected because LikeC4 metadata is
string-valued and nodes spanning languages are rare outside this repo's mirrored layout; inferring a node's
language from its `root_package` prefix, rejected because it forbids equal root package names and keeps the
language split invisible in the model. Element ids become fully qualified (`python.core`) everywhere, which
re-blesses every model-truth golden once (stated in the commit).

### D2 — Root-relative relations and scoped views
`c4` resolves a relation line at depth one inside a root as `<root>.<endpoint>` (LikeC4's lexical scoping), keeps
`c4.relation-in-body` for deeper bodies and adds a finding for relations outside roots. Views must be
`view <id> of <root>`: `c4` strips the root prefix to build a root-local projection of the model (elements,
relations, kinds) and runs today's expansion, depth and mermaid code on that projection unchanged. That is what
makes wrapped diagrams byte-identical, by construction rather than by careful re-counting. Alternative: model-level
fully qualified relations and unscoped views with `include python.*`, rejected as churning every relation and view
line of every repo.

### D3 — Facts, not findings, cross the twin boundary
`archcheck` asks a per-language facts provider for: unit statuses (present / missing / ambiguous + sorted
candidates) for every declared and derived unit, top-level units, and element-level edges with one witness. The
native provider calls `lang`; the foreign provider calls `twin`, which runs `la-arch-check --language L --emit
facts` and validates the JSON against `shared/schema/facts.schema.json`. All claims math and model-truth run in
`archcheck` on facts. Alternatives: forwarded twin returns rendered findings (wrong dead/shadowed results when a
node exists in one language only; duplicate neutral findings); passing the unit list in argv (the forwarded twin
can derive it from the same model and index with its own neutral `c4`/`archcheck` code). Determinism: adapters
iterate source modules and targets in sorted module-id order and keep the first witness per element edge; the
union keeps the first language in id order; model-truth findings keep today's order (missing edges sorted, then
arrows in model order).

### D4 — The `twin` node
Discovery, the identity handshake, runner probing, wholesale forwarding and facts transport live in a new `twin`
node in both twins, with arrows `cli -> twin`, `archcheck -> twin`, `twin -> contract`. Alternative: `cli` injects
a facts provider into `archcheck`, rejected because `cli` would have to read the index to know which languages
to forward, duplicating `archcheck`. Runner and install commands per language live in `languages.yaml`; hint
texts in `findings.yaml`.

### D5 — Discovery by identity on PATH
Both twins install identical command names, so the first `la-arch-check` on PATH may be either twin. Discovery
enumerates PATH directories (deduplicated by real path) plus `<repo>/node_modules/.bin`, runs each
`la-doctor --twin`, and accepts only a matching (language, version, contract hash). The runner is probed with the
same handshake before any real command runs through it, because a runner's own download failure exits 1, which a
wholesale-forwarded command would otherwise report as "violations". No timeouts: a large repo's facts run is
legitimately slow. `LA_FORWARDED=1` on every forwarded process is a guard against wrappers misreporting identity;
the protocol is loop-free without it (facts requests are only served natively, and only the npm twin forwards the
Python-only commands). Runners were checked: `uvx --from pkg==X` does not reuse a `uv tool install` and `npx -p`
does not reuse a global install, hence PATH discovery first.

### D6 — TypeScript adapter
- Source enumeration walks `<source_root>/<root_package>` itself (not tsconfig file lists): extensions from
  `languages.yaml`, minus test globs, `*.d.ts` and `node_modules`; symlinks followed only while the real path stays
  under `source_root`, with a visited set against cycles.
- tsconfig: section `tsconfig`, else nearest `tsconfig.json` upward, else defaults with `moduleResolution:
  bundler`. Parsed with `ts.readConfigFile` + `ts.parseJsonConfigFileContent` (JSON only, `extends` included).
  `allowJs` is forced on only in the options passed to `ts.resolveModuleName`; project membership is unaffected.
- Project references: depth-first preorder over parsed referenced configs, cycle-tolerant via a visited set; a
  file's owner is the first project whose `fileNames` contain it, else the root config. While loading, each
  referenced project's inputs are mapped forward with `ts.getOutputFileNames`; the inverse map (declaration
  output → source) redirects resolutions. An output not in the map is taken as the file it is (a `.d.ts` is
  invisible, so the import is unattributed).
- Classification (spec "TypeScript module resolution"): resolve first, so `paths` aliases resolve internally; then
  builtin / `node_modules` / unresolved bare → external; real path outside `root_package` → unattributed;
  unresolved relative → lexical candidate (normalized, `?`/`#` suffix and source extension stripped, containment
  checked).
- Type-only decision table, by syntax node (TS 6 AST):

  | node | counts as runtime edge when |
  |---|---|
  | `ImportDeclaration` | not `importClause.isTypeOnly`, and (no clause, default/namespace binding, or ≥1 named element without `isTypeOnly`) |
  | `ExportDeclaration` with `moduleSpecifier` | not `isTypeOnly`, and (`export *`, `export * as ns`, or ≥1 element without `isTypeOnly`) |
  | `ImportEqualsDeclaration` with `ExternalModuleReference` | not `isTypeOnly` |
  | `CallExpression` `import(...)` | argument is a string literal |
  | `CallExpression` `require(...)` (identifier callee) | argument is a string literal |
  | `ImportTypeNode`, `/// <reference>`, JSDoc `@import` | never |

### D7 — Units in segment form
The neutral core handles units as segment lists; Python joins with `.`, TypeScript with `/`. Unit status is a
language-adapter fact, so Python keeps its present/missing semantics (no ambiguity) and only TS can report
ambiguity. Edge attribution remains longest-unit-prefix over module ids, so ambiguity does not affect it.

### D8 — npm twin shape
`node/` with `package.json` (`type: module`, `engines.node >= 22`, `"private": true`, `files`: `dist`, contract
data, README, LICENSE), `tsconfig.json` (strict, `module: nodenext`), ESLint flat config with typescript-eslint,
Vitest. `src/<node>/` mirrors the Python nodes (contract, config, cli, c4, archcheck, lang, review, doctor, twin).
The CLI parser is hand-written from `cli.yaml` (no library reproduces argparse's no-abbreviation / `--` /
passthrough / `require_one_of` semantics with exit 2 exactly). One generated bin file per manifest command,
`dist/bin/<command>.js`, each calling the shared dispatcher with its command name; a test pins `package.json`
`bin` to the manifest set. Contract data is copied into `dist` at build. `yaml` is configured `version: '1.1'`,
`uniqueKeys: false`; JSON Schema validation uses `ajv` (draft 2020-12).

### D9 — Conformance: one runner, explicit twin
The Python runner's case model separates `fixture_languages` (all listed overlays applied in list order to one
repo; a later overlay overwrites an earlier one's file), the invoking twin (which bin directory is first on PATH;
both twins' bin dirs are present so forwarding works), and the golden variant (paired cases: `stdout.<language>`).
Native selection per twin: fixture languages ⊆ {own} and the command is native to that twin.
`scripts/conformance-cross` runs every case through both twins. `npm run conformance` in `node/` calls the Python
runner with the node bin dir (contributors need `uv`; users never run it). The fake `gh` stays the runner's Python
script; the planned bash + jq port is dropped because nothing else needs it.

### D10 — Publish gating and versions
`node/package.json` starts at 0.2.1 with the other two versions (no bump; releases bump). The publish workflow
first checks that both snapshots' `CONTRACT_HASH` and both package versions equal the tag, else publishes neither.
The npm job (trusted publishing, OIDC) logs a skip while `"private": true`. PR 4 (DEV-2027) removes the flag; npm
trusted publishing must be configured on npmjs.com for the package, which likely requires the package to exist
first (a one-time manual publish).

### D11 — Target-tag ids outside ASCII
`shared/regex-subset.md` already scopes parity to ASCII input. Both twins treat a `[target: …]` id containing a
non-ASCII character as not matching before applying the regex, instead of translating `\d \w \s \b` and their
complements.

## Risks / Trade-offs

- [The TS 6.0 compiler API is the last stable JS API; 7.x is native] → pinned `~6.0` as a runtime dependency;
  revisit when 7.x stabilizes a programmatic API.
- [Our scoped-view and root-relative relation subset might not be valid LikeC4] → run `npx likec4 validate` on
  this repo's migrated model and on the migrated fixtures once at implement time (manual; needs network).
- [Process spawns per discovery probe] → a few tens of ms per candidate; acceptable for a CLI.
- [Every arch-check golden changes once (qualified ids)] → one re-bless commit with the stated reason; diagram
  goldens must stay byte-identical, which is itself the regression proof for D2.
- [Contributors need both toolchains for conformance] → documented in AGENTS.md; users never do.
- [npm twin forwards the Python-only commands, so a TS-only repo cannot run them before PR 3/4] → unchanged in
  effect: they have no TS implementation yet.

## Migration Plan

Per target repo, once: move `root_package`/`source_root` into a `python:` (or `typescript:`) section of
`index.yaml`; wrap every top-level model element and relation in `<language> = system '<title>' { … }`; add
`of <language>` to every view; qualify `cross_cutting_specs.touches`; rename repo-owned keys to `x-…`; run
`la-arch-check` until clean. Diagrams need no regeneration. Rollback is reverting to the previous release.
