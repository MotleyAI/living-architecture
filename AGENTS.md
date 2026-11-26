# Working in this repo

## The twin rule

The repo ships two packages: `type-rename-move` (the `trmv-*` commands, plugin `plugin/trmv`) and
`living-architecture` (the `la-*` commands, plugin `plugin/la`), which depends on trmv and never the reverse. Each has
one contract and one implementation per ecosystem: the PyPI packages in `python/trmv` and `python/la` (Python target
repos, one uv workspace) and the npm packages in `node/trmv` and `node/la` (TS/JS target repos, one npm workspace).
Every behaviour observable through a command must be identical in both twins for the languages they share, on every
input in the forms the tools and docs write. The conformance corpus decides: an output that differs from its golden
is a bug in the twin, never in the golden.

Only `shared/trmv/` and `shared/la/` are the source of truth for parameters, defaults, user-facing texts and command
surfaces. Code never hard-codes them; each twin loads its vendored copy of its package's directory at runtime.

## Changing a parameter, finding, flag or rule

1. Edit the owning package's directory under `shared/`: a schema under `schema/`, a template in `findings.yaml`, a
   command in `cli.yaml`, a rule in `conventions.yaml` (la), a language fact in `languages.yaml` (trmv), or a script
   under `scripts/` (la).
2. Run `scripts/sync-shared` to refresh every twin's snapshot.
   A drift test fails until you do.
3. Update every twin's code to match.
4. Add or adjust a conformance case under `conformance/<package>/cases/` (the package whose command it invokes) and
   list it in that tree's `INVENTORY.md`. Every `findings.yaml` template of a package must be produced by at least
   one golden of its tree.

## Conformance case kinds

- **neutral**: one expected output, run by every twin.
- **paired**: a per-language fixture overlay (`python/`, `node/`); goldens shared or per language
  (`stdout.<language>`).
- **adapter**: one language only.

A case may pin the invoking twin (`twin:`); otherwise its output must not depend on which twin runs it. The
case format is in `conformance/README.md`.

## Goldens

Write goldens only with `LA_UPDATE_GOLDENS=1`, and only with a stated reason in the commit message (a
deliberate behaviour change, or a new case). Review the golden diff like code. Never regenerate a golden to
absorb a difference you cannot explain. Cases marked `golden: manual` pin new behaviour and are edited by
hand. The update mode always runs serially, even with `-n`.

## Versions and the contract hash

The four package versions (`python/{trmv,la}/pyproject.toml`, `node/{trmv,la}/package.json`) and both
`plugin/{trmv,la}/.claude-plugin/plugin.json` always move together, and la pins trmv to the same minor (its
`pyproject.toml` dependency, its `package.json` dependency and its plugin's `dependencies`). A release that changes
the tool inputs (`shared/`, `conformance/`, the twins' sources and build inputs, their manifests and lockfiles beyond
the versions and la's pin) raises the minor or major version, so every release in a minor series ships the same
tools; a test checks it on the bump PR and `scripts/release-check` at publish time. Skills compare only major.minor of
the tools against their plugin's `plugin.json` (`trmv-doctor --plugin`, `la-doctor --plugin`). Each snapshot's
`CONTRACT_HASH` must equal the hash of its package's `shared/<package>/`; `trmv-doctor --contract-hash` and
`la-doctor --contract-hash` print the bundled ones. Release only when every twin's version and contract hash agree.

## Dev and test commands

PyPI twins, in `python/trmv` and `python/la` (one uv workspace; `uv sync --all-packages` in `python/`):

```bash
uv run pytest -q                  # the package's full suite in parallel (-n auto), including its conformance corpus
uv run ruff check src tests
uv run basedpyright -p .. src tests
```

npm twins, in `node/` (one npm workspace; the conformance runner is the Python one, so it needs `uv sync
--all-packages` in `python/`):

```bash
npm ci
npm run lint && npm run typecheck
npm test                          # Vitest over both workspaces, including the npm pack smoke tests
npm run build && npm run conformance   # both corpora through the npm twins' bins
```

Repo-wide: `scripts/sync-shared [--check]`, `scripts/conformance-cross [--twin <python|typescript>]` (every
case through both twins, or through one), `la-arch-check` (this repo's own architecture, from either twin), and
`npx -y @anthropic-ai/claude-code plugin validate plugin/trmv` (and `plugin/la`).

Tests run in parallel by default; pass `-n 0` to pytest (also through `npm run conformance` and
`scripts/conformance-cross`) to debug serially. A test never writes to a shared checkout path or a fixed
external path, only under its own temporary directory.

Both twins implement the `trmv-*` commands natively for their own language and route each input by its file
language: the other language's files run in the other twin (found by `trmv-doctor --twin` on `PATH`, else
`uvx`/`npx`; la's commands use `la-doctor --twin`), whose output is captured and printed as its block in registry order; `trmv-refactor` on the other
language's source hands its raw arguments to that twin. `la-check-conventions` and `la-count-comments` are
neutral: the other language's files come back as a conventions-facts document (`la-check-conventions --language
L --emit facts`, paths on stdin).
`trmv-typecheck` runs the other language's section as `trmv-typecheck --language L` in its twin; `la-typecheck` is its
deprecated alias until 0.15.0.

Integration tests run a real checker and are deselected by default: `uv run pytest -m integration` in
`python/trmv`, `npm run build && npm run test:integration` in `node/`.
