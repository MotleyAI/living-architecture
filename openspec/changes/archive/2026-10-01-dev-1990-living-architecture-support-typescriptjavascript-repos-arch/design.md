## Context

See proposal.md (Why). Today one PyPI package holds every command. Its only third-party runtime
dependencies are `pyyaml`, `pydantic` and `rope`. No tool imports or executes target-repo code: everything
reads files as text through stdlib `ast`/`tokenize`, plus YAML. The one exception is `dr-refactor`, which
may run under the project venv so that rope can resolve third-party types. Node is already a prerequisite
for every repo, because the OpenSpec and LikeC4 CLIs run via `npx`. `typescript@latest` is 7.x, the native
port, and its programmatic API is `unstable/*`; 6.0.x is the last line with the stable JS compiler API.

This change is PR 1 of 4. The design below covers all four PRs, so that PR 1 fixes the contract PRs 2–4 are
written against.

## Goals / Non-Goals

**Goals:**
- A TS-only setup needs no Python, and Python repos keep fully native Python tooling.
- One contract, two native implementations, with drift caught by machines rather than by review.
- Python's observable outputs are frozen before anything moves.

**Non-Goals:**
- Languages beyond Python and TS/JS (the design leaves room for them).
- Multi-package workspaces. Multi-language repos get only per-language roots (PR 2).
- Shared parser error text and `--help` text.

## Decisions

### D1 — Two native twins, native-only languages
The PyPI `living-architecture` package analyses Python targets and the npm `living-architecture` package
(unscoped, name free) analyses TS/JS targets. Only the language-neutral core is implemented twice. Each
language adapter exists once, in its own twin, using that ecosystem's exact parser (`ast` / the TS compiler
API).

Alternatives considered:
- One TS toolchain with a Python adapter. Rejected: it loses Python-nativeness.
- Freezing Python into npm binaries. Rejected: a build-matrix burden, and Node is still needed for TS.
- Both twins analysing both languages. Rejected: it doubles the hardest-to-sync part and forces approximate
  parsers.

### D2 — Symmetric layout
The layout is `python/`, `node/` (from PR 2), and a root that holds only shared things: `shared/`,
`conformance/`, `plugin/`, `architecture/`, `openspec/`, `scripts/`, `AGENTS.md`, `CLAUDE.md`. Root
`README.md` and `LICENSE` are vendored into `python/` (and later `node/`) by `scripts/sync-shared`, so each
package builds self-contained.

Alternative considered: Python at the root plus `node/`. Rejected as asymmetric, with shared scripts living
inside one twin.

### D3 — Shared contract as vendored runtime snapshots
`shared/` holds the source of truth:

```
shared/
  schema/living-architecture.schema.json   # keys, types, bounds, if/then cross-field rules, defaults
  schema/index.schema.json                 # index.yaml shape; never rejects what is a finding today
  findings.yaml                            # id -> template ({name}, {name!r}), incl. gate verdicts/hints
  cli.yaml                                 # commands, subcommands, options, types, choices, repeatable,
                                           #   required, positionals, passthrough, exit codes, help
  conventions.yaml                         # rule ids, per-language descriptions, waiver syntax, ratio default
  languages.yaml                           # per language: source extensions, test globs, suppression, waiver prefix
  regex-subset.md / vectors                # the portable issue_key_pattern subset + accept/reject vectors
  vectors/                                 # repr, glob, default-expansion vectors (consumed by both suites)
  scripts/*.sh                             # review helpers (bash, gh, jq)
```

`scripts/sync-shared` copies `shared/` into `python/src/living_architecture/contract/data/` (and
`node/src/contract/data/` from PR 2). The copy is byte-exact, preserves file modes, and writes
`CONTRACT_HASH`, a sha256 over the sorted (path, executable bit, bytes) of the snapshot (git tracks no other
mode bits). Installed tools always load
their bundled snapshot through module-relative resource paths; root `shared/` is never read at runtime.
`la-doctor --contract-hash` prints the bundled hash. A
drift test in each suite compares snapshot and source. CI builds the artifacts (wheel and sdist; `npm pack`
from PR 2), installs them outside the checkout, loads the contract, runs a review shim, and checks the
hash. The release workflow refuses to publish when the twins' hashes or versions differ.

Alternative considered: goldens only, with each twin hard-coding its own values. Rejected because
parameters and texts not hit by a golden would drift silently.

### D4 — Default materialization and validation
Both twins share one algorithm, which is not validator-specific:
1. Parse the YAML with the fixed profile: YAML 1.1 as PyYAML's safe loader reads it, with the last
   duplicate key winning. The Node twin configures `yaml` (`version: '1.1'`, `uniqueKeys: false`).
2. Validate against the schema with `additionalProperties: false` and `if/then` cross-field rules (Python:
   `jsonschema`; Node: `ajv`).
3. Materialize defaults recursively. An absent object property whose schema has a `default`, or whose
   sub-schema has defaulted properties, is created. Explicit values are never replaced.
4. Build the typed model. The pydantic models declare no defaults, so the schema is the only source of
   defaults.

`issue_key_pattern` is checked against the portable regex subset by a small shared syntax check, then
compiled natively with full-match semantics. Shared input → resolved-output vectors are run through
`la-config show`.

### D5 — Findings registry and canonical repr
Every printed finding, verdict and hint is rendered from `findings.yaml`. `!r` is allowed only on normalized
values (str, int, float, bool, null, list, mapping). The canonical repr is Python's `repr` for those types:
for strings, the quote choice, the escapes for `\\`, `\n`, `\r` and `\t`, and the `\xNN`/`\uNNNN`/`\UNNNNNNNN`
escapes for non-printables. It is written down in the contract and pinned by `shared/vectors/repr.yaml`.
Callers normalize raw YAML and validator values before rendering. A coverage test requires every registry id
to appear in at least one golden.

### D6 — CLI from the manifest
Each twin builds its native parser from `cli.yaml` with these semantics:
- no abbreviation (`allow_abbrev=False`)
- `--` honoured
- usage error → exit 2
- `passthrough` commands get raw argv (`la-count-comments` and the review shims)
- handlers return the exit code

Conformance pins accepted and rejected invocation vectors by exit code and resulting behaviour, not parser
error text. `test_skills` checks skill command references against the manifest. The entry-point set must
equal the manifest command set.

### D7 — Conformance corpus
Each case lives in `conformance/cases/<id>/`:

```
case.yaml        # kind: neutral|paired|adapter; languages; command; args; cwd; env extras;
                 #   git: [ {commit|branch|stage|modify|delete|rename|untracked ...} ]  (deterministic history,
                 #   local bare origin, fixed identity/dates); expect: {exit}
repo/            # shared fixture files
python/ node/    # per-language overlays (paired/adapter cases)
stdout[.python|.typescript]  stderr[...]   # goldens (per-language only where witnesses differ)
```

The runner materializes the case into a temporary directory with a fixed environment (`LC_ALL=C`, `TZ=UTC`,
`COLUMNS=80`, `GIT_*` identity and dates, no network) and runs the installed command as a subprocess. It
normalizes only the temporary root, to `<ROOT>`, and compares bytes. `LA_UPDATE_GOLDENS=1` writes goldens;
otherwise the run only diffs. **PR 1 freezes the goldens from the pre-restructure tool before any code
moves.** Version-dependent texts (e.g. `SyntaxError.msg` across 3.11–3.13) either get a dedicated
normalization declared in `case.yaml` or are avoided. The goldens must pass across the whole CI Python
matrix. Golden regeneration rules are in AGENTS.md.

### D8 — Python node decomposition (mirrored by the npm twin)
| node | contents (PR 1 source) |
|---|---|
| `contract` | snapshot loading, template rendering, canonical repr, glob dialect, default materialization, regex-subset check |
| `config` | `config.py`; repo-root discovery; resolved `LaConfig` |
| `cli` | every `main()`; parsers built from the manifest; dispatch to node handlers; pyproject scripts point here |
| `c4` | `arch_diagrams.py` (constrained `.c4` parser, views, mermaid) |
| `archcheck` | `arch_check.py`, language-neutral: claims/children/arc42/identity/spec-mapping/ratchet/tags/model-truth math, `license()` |
| `lang` | Python `ast`/`tokenize`: unit discovery under `source_root`, runtime import targets (TYPE_CHECKING excluded), conventions rule detectors, comment and docstring line sets. Returns data only. |
| `conventions` | `conventions.py` framework (git diff, waivers, text-ratio aggregation, report) + `comment_count.py` |
| `review` | `shims.py`; script paths from `contract` |
| `doctor` | `doctor.py`; reports version and contract hash |
| `refactor` | the former `deterministic_refactor` package (rope, compliance, mock lint), moved without a compatibility shim |

Import law (the model's arrows):
- `cli → contract, config, archcheck, c4, conventions, review, doctor, refactor`
- `archcheck → c4, lang, config, contract`
- `conventions → lang, config, contract`
- `c4 → contract`
- `config → contract`
- `review → config, contract`
- `doctor → config, contract`
- `refactor → contract`
- `lang` and `contract` → nothing internal

`__version__` stays in the root `__init__.py`. The root package is unclaimed, so importing it measures as no
edge. Draft model, refined at implement time (any `architecture/` edit needs the user's per-edit OK):

```
specification {
  element node
  tag legacy
  tag virtual
}
model {
  contract = node 'Shared contract'
  config = node 'Config'
  cli = node 'CLI'
  c4 = node 'LikeC4 model'
  archcheck = node 'Architecture check'
  lang = node 'Language adapter'
  conventions = node 'Conventions and comments'
  review = node 'Review shims'
  doctor = node 'Doctor'
  refactor = node 'Deterministic refactoring'
  cli -> contract
  cli -> config
  cli -> archcheck
  cli -> c4
  cli -> conventions
  cli -> review
  cli -> doctor
  cli -> refactor
  archcheck -> c4
  archcheck -> lang
  archcheck -> config
  archcheck -> contract
  conventions -> lang
  conventions -> config
  conventions -> contract
  c4 -> contract
  config -> contract
  review -> config
  review -> contract
  doctor -> config
  doctor -> contract
  refactor -> contract
}
```

`index.yaml` (draft): `source_root: python/src`, `root_package: living_architecture`, one precise node per
package above, `legacy_arrows: {baseline: 0}`, and `diagrams: {architecture/system.arc42.md: [system]}`.
The `specs:` / `cross_cutting_specs` mapping is added only at archive time (pr-review), because mapping a
spec directory before it exists is itself a finding. The plan there: `arch-check` → node `archcheck`
`specs:`; `shared-contract` → `cross_cutting_specs` touching every node.

Draft `system.arc42.md` principles (exact wording to be approved per edit):
1. Twins: every behaviour observable through a command is identical in both implementations for the
   languages they share; the conformance corpus decides.
2. Parameters, defaults, user-facing texts and command surfaces come only from the shared contract.
3. Language-specific code lives only in `lang` and `refactor`.
4. Tools never import or execute target-repo code.

### D9 — `source_root`
`repo_root` and `source_root` are threaded separately through the architecture API. Architecture, docs and
specs resolve from `repo_root`; code resolves from `source_root`. `source_root` is validated: it must be
relative, without `..`, must not resolve outside the repo (including via symlinks), must be a directory, and
must contain `root_package`. Otherwise the result is exit 2. Module ids stay prefix-free. `license()` keys
its cache on the repo root.

### D10 — Roadmap (PRs 2–4, recorded so PR 1's contract fits them)
- **PR 2 (DEV-2025): npm twin + TS arch-check + forwarding**
  - TS/ESM, strict, tsc build, Vitest, ESLint/typescript-eslint, Node ≥ 22.
  - Twin of `contract`, `config`, `cli`, `c4`, `archcheck`, `review`, `doctor`, plus the TS `lang` part 1.
  - TS units use the existing keys in path notation (`root_package: src`, `package: src/daemon`,
    `children: [pty]`, `claims: [src/cli]`). Units are extensionless and resolve to a dir or exactly one
    module file (`.ts`, `.tsx`, `.mts`, `.cts`, `.js`, `.jsx`, `.mjs`, `.cjs`); ambiguity is a
    `claims-exist` finding. The core works on segment lists, splitting on `.` or `/`.
  - Invisible to arch-check: test globs, `*.d.ts`, `node_modules`. The root barrel `src/index.*` is exempt
    like the root `__init__.py`.
  - Import edges come from `typescript@~6.0`: static, re-export, side-effect, `import()` and `require()`,
    resolved by `ts.resolveModuleName` under the repo's parsed tsconfig (paths, baseUrl, moduleResolution,
    `.js`→`.ts`, barrels, project references). Type-only is syntactic (`import type`, `export type`,
    all-`type` specifiers); bare specifiers are external.
  - Multi-language `index.yaml`: `languages:` roots plus per-node `package: {python: …, typescript: …}`; the
    single-language form is unchanged. arc42 principle items may carry `[lang: <language>]`, validated
    against the declared languages; untagged binds every twin.
  - `language:` config key plus auto-detection (pyproject.toml/setup.py → python; package.json +
    tsconfig.json → typescript; both or neither → exit 2).
  - Forwarding: a language-specific command run in the other language's repo uses a locally installed twin
    at the same version first, otherwise `npx -y -p living-architecture@<ver>` or
    `uvx --from living-architecture==<ver>`. Offline or unpublished → exit 2 with a hint. A command never
    forwards inside its own language's repos, and a test proves it. Neutral commands never forward.
    Multi-language `la-arch-check` checks its native side and forwards a language-only run for the others.
  - The npm publish job lands here; the first public npm release happens only at PR 4.
  - The fake `gh` used by review-script tests is ported to bash + jq, so both suites can share it.
- **PR 3 (DEV-2026): TS conventions + comments + `la-typecheck`**
  - `import-not-top` follows the TS convention: static imports after other statements and non-top-level
    `require()` are flagged; `import()` is allowed and type-position `import()` ignored.
  - The other rules: text-ratio (`//`, `/* */`, JSDoc), composite-assert (`expect(a && b)`,
    `assert(a && b)`), raises-single-throw (`toThrow`, `rejects`, `assert.throws`/`rejects`). Waivers are
    `// ALLOW(rule): reason`.
  - `la-count-comments` counts JSDoc as doc lines.
  - `la-typecheck [--write-baseline]` in both twins. Python passes through to basedpyright. npm runs the
    repo's own tsc against `.tsc-baseline.json` (a multiset of (file, code, message), auto-shrinking).
    Suppression is `// @ts-expect-error — <reason>`, never `@ts-ignore`.
  - New config key `commands.typecheck`.
- **PR 4 (DEV-2027): TS `dr-*`, neutral skills, README, acceptance**
  - TS LanguageService refactors; `dr-compliance` via tsconfig flags plus explicit `any`; `dr-mock-lint` for
    untyped `vi.fn()`/`jest.fn()`/`vi.mock`.
  - Skills become language-neutral: facts via `la-config get lang.<key>`, idioms in
    `plugin/languages/<lang>.md`, and a leak test.
  - README TS claims and the first public npm release.
  - Acceptance: a Node-only clean-container run asserts that no `python`, `uv` or `uvx` is ever invoked,
    plus the worktree-term Init and `/la:pr` run.

## Risks / Trade-offs

- [Goldens freeze accidental behaviour, including bugs] → Freezing is deliberate: a bug fix becomes an
  explicit golden update with a stated reason (AGENTS.md rule), reviewed in the diff.
- [The canonical repr or YAML profile is hard to reproduce in Node] → Both are pinned by shared vectors that
  Node must pass in PR 2. The scope is limited to normalized values.
- [Two copies of the neutral core still drift in logic that no case exercises] → Every registry id has a
  coverage requirement; neutral and paired cases run in both twins; the import structure is enforced by one
  model.
- [Dropping argparse abbreviations breaks someone's muscle memory] → Accepted. The change is documented as
  BREAKING (minor).
- [Rejecting non-portable `issue_key_pattern` breaks an exotic config] → None is known. The error names the
  key and points to the subset.
- [Moving packages breaks in-process importers] → Only this repo's tests import them. Documented as BREAKING
  for in-process importers.

## Migration Plan

Users reinstall from the same version: `uv tool install living-architecture==<ver>`, or
`uv tool install -e <checkout>/python` for an editable install. Command names, flags and outputs are
unchanged apart from the documented exceptions. Rollback is reverting the PR; no persisted state changes.
