## Why

Deterministic refactoring has grown into a tool that is useful on its own (about 10.8k of the Python twin's 18k lines
and 5k of the npm twin's 13k), and its dependency on the rest of the repo already runs one way. People who only want
verified renames and moves should be able to install it without the architecture workflow.

## What Changes

- Two packages and two Claude Code plugins in this repo, released in lockstep at 0.13.0:
  `deterministic-refactor` (plugin `dr`: the language-server layer, the type-check gate, refactor, compliance,
  mock-lint) and `living-architecture` (plugin `la`: the architecture model and checks, diagrams, conventions, review
  helpers, affected tests and the PR flow), which depends on dr and pins it to the same minor. dr never depends on la.
- Each package has two twins: a uv workspace under `python/` (`dr/`, `la/`, a dev-only conformance runner) and an npm
  workspace under `node/` (`dr/`, `la/`).
- `shared/` splits into `shared/dr/` and `shared/la/`, each with its own snapshot and contract hash.
- **BREAKING** `la-typecheck` is renamed `dr-typecheck`; `la-typecheck` stays one minor as an alias that prints a
  deprecation line on stderr.
- New commands `dr-doctor` and `dr-config`; `la-doctor` also runs dr's checks and reports a missing or mismatched dr.
- A dr-only repo configures dr in `deterministic-refactor.yaml`; a repo using la keeps one `living-architecture.yaml`.
  Both present is refused. Each file has its own format series.
- **BREAKING** `conventions.exempt` becomes a top-level `exempt` key defined by dr and read by language detection and
  the conventions gate; `living-architecture.yaml` moves to format 0.13.0 and `la-arch-migrate` moves the key.
- `architecture/index.yaml` gains a Python-only `source_roots` list, so one language's root packages can sit under
  several import roots (a uv workspace).
- **BREAKING** The skills `deterministic-refactor`, `make-refactor-target-compliant` and `make-diff-compliant` move to
  the `dr:` namespace (no stubs), with a new `dr:init`; la's plugin declares a dependency on the dr plugin.
- The conformance corpus splits into `conformance/dr/` and `conformance/la/`, run by one package-aware runner.
- This repo's architecture model gets `dr` and `la` nodes per language with `la -> dr` the only cross arrow.

## Capabilities

### New Capabilities
- `doctor`: what `dr-doctor` and `la-doctor` check across the two packages: plugin versions, config, executables, the
  dr installation la needs, the twin identity lines and the contract hashes.

### Modified Capabilities
- `arch-check`: Python `source_roots` in `architecture/index.yaml`.
- `repo-config`: the two config files and their resolution, the both-files refusal, per-file format series, the
  top-level `exempt` key and its migration, `dr-config`.
- `shared-contract`: the contract splits per package, each with its own snapshot and hash, and each package's command
  set comes from its own `cli.yaml`.
- `typecheck`: the command is `dr-typecheck`, with the deprecated `la-typecheck` alias.
- `twin-forwarding`: each package forwards through its own identity handshake, runner and install hint.
- `conventions`: the gate's exemptions come from the top-level `exempt`.

## Impact

- Code: every module of both twins moves into a package (`deterministic_refactor`/`living_architecture`,
  `node/dr`/`node/la`); la imports dr's `contract`, `config`, `lang`, `twin` and `changes` as a library.
- Distribution: a new PyPI and npm package `deterministic-refactor`; `living-architecture` depends on it; a second
  plugin `dr` in the marketplace; install hints change.
- Target repos: `living-architecture.yaml` needs `la-arch-migrate` (0.4.0 to 0.13.0); scripts calling `la-typecheck`
  should switch to `dr-typecheck` before 0.14.0; references to `la:deterministic-refactor` and friends become `dr:`.
- Repo: `shared/`, `conformance/`, `plugin/`, `architecture/`, CI, publish, `scripts/` and docs.
