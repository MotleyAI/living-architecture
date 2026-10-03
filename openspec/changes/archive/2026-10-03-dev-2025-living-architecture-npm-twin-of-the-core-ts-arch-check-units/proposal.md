## Why

TS/JS repos cannot use the living-architecture commands without a Python toolchain, and the arch-check cannot
measure TypeScript imports at all. This is PR 2 of 4 under DEV-1990: it adds the npm twin of the
language-neutral core, the TS arch-check adapter (units and import edges), and forwarding between twins, so
either twin checks a Python, TS or mixed repo with identical output. It also gives `index.yaml` and the model a
shape where each language owns one root, which a mixed repo needs.

## What Changes

- **npm twin** `living-architecture` under `node/`: TypeScript (strict, ESM), Node ≥ 22. It twins the
  language-neutral core (contract, config, cli, c4, archcheck, review, doctor) plus a TS `lang` adapter and a
  `twin` node, with the same command names, flags and exit codes, built from the shared CLI manifest. It ships as
  `"private": true` until PR 4 (DEV-2027); the publish job lands here.
- **BREAKING** `architecture/index.yaml`: one section per language (`python:`, `typescript:`) holding
  `source_root` and `root_package` (and `tsconfig` for TS); the top-level `root_package`/`source_root` are
  removed. Top-level `x-*` keys are accepted and ignored by the tools.
- **BREAKING** model: one top-level root element per declared language, whose id is the language. Nodes are the
  root's children; relations live inside a root with names relative to it; element ids are fully qualified in
  findings and in `cross_cutting_specs.touches`.
- **BREAKING** views are scoped to one root (`view <id> of <root>`); the root is never drawn, so migrated
  diagrams stay byte-identical.
- **TS adapter, part 1**: units in path notation, test files / `*.d.ts` / `node_modules` invisible, import edges
  from the TypeScript 6.0 compiler API under the repo's tsconfig (paths, baseUrl, moduleResolution, project
  references), type-only imports excluded syntactically.
- **Multi-language arch-check**: each declared language's facts (unit existence, top-level units, witnessed
  edges) come natively or from the other twin; claims and model-truth math run once, model-truth over the union
  of edges, in one output order whichever twin is invoked.
- **Twin forwarding** (both twins): discovery on PATH by a `la-doctor --twin` identity handshake (language,
  version, contract hash), else through `npx`/`uvx`; unreachable twin → exit 2 with an install hint. In this PR
  the npm twin forwards the Python-only commands (`la-check-conventions`, `la-count-comments`, `dr-*`) wholesale.
- arc42 principle items may carry `[lang: <language>]`, validated against the declared languages.
- `[target: …]` tag ids containing non-ASCII characters never match `issue_key_pattern` (twin parity).
- Conformance: the case model separates the invoking twin from the fixture languages; one runner drives both
  twins; a cross-twin job runs every case through both twins' entry points.
- This repo's own architecture becomes a two-root model (approval-gated edits).

## Capabilities

### New Capabilities
- `twin-forwarding`: how a twin identifies, finds and invokes the other twin, which commands forward, and how
  forwarding fails.

### Modified Capabilities
- `arch-check`: per-language index sections and model roots, relations and views scoped to a root, fully
  qualified ids, `x-` keys, `[lang:]` tags, the TS units and import-edge rules, and multi-language checking.
- `shared-contract`: target ids outside ASCII never match, the manifest's internal options and per-command
  native languages, TS test globs, a snapshot per twin, and the conformance case model with cross-twin runs.

## Impact

- `shared/`: `schema/index.schema.json`, new `schema/facts.schema.json`, `findings.yaml`, `cli.yaml`,
  `languages.yaml` (TypeScript entry, runner and install commands), `regex-subset.md`, vectors. Both snapshots
  re-synced; the contract hash changes.
- Python twin: `c4` (roots, root-relative relations, scoped views), `archcheck` (facts, union model-truth,
  ordering, `x-` keys, `[lang:]`), `doctor` (`--twin`), `cli` (internal options), new `twin` node.
- New `node/` package; dependencies `typescript@~6.0`, `yaml`, `ajv`.
- Conformance: every arch-check and diagrams fixture migrates to language roots (goldens change where ids become
  qualified), TS overlays, multi-language, forwarding and cross-twin cases; runner case model.
- CI: node job, npm pack smoke test, cross-twin job; publish workflow pre-check and gated npm job.
- `architecture/` (this repo), `AGENTS.md`, `README.md`, the `living-architecture` and `arch-slice` skills.
- Target repos migrate once: wrap the model in a language root, move `root_package`/`source_root` into the
  language section, add `of <root>` to views, qualify `touches`.
