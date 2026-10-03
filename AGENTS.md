# Working in this repo

## The twin rule

The `la-*`/`dr-*` commands have one contract and one implementation per ecosystem: the PyPI package in
`python/` (Python target repos) and the npm package in `node/` (TS/JS target repos). Every behaviour observable through a command must be identical in both twins for the languages they
share. The conformance corpus decides: an output that differs from its golden is a bug in the twin, never
in the golden.

Only `shared/` is the source of truth for parameters, defaults, user-facing texts and command surfaces.
Code never hard-codes them; each twin loads its vendored copy of `shared/` at runtime.

## Changing a parameter, finding, flag or rule

1. Edit `shared/`: a schema under `schema/`, a template in `findings.yaml`, a command in `cli.yaml`, a rule
   in `conventions.yaml`, a language fact in `languages.yaml`, or a script under `scripts/`.
2. Run `scripts/sync-shared` to refresh every twin's snapshot (and the vendored `README.md`/`LICENSE`).
   A drift test fails until you do.
3. Update every twin's code to match.
4. Add or adjust a conformance case under `conformance/cases/` and list it in `conformance/INVENTORY.md`.
   Every `findings.yaml` template must be produced by at least one golden.

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
hand.

## Versions and the contract hash

The package versions (`python/pyproject.toml`, `node/package.json`) and
`plugin/.claude-plugin/plugin.json` always move together, as do the skills' `la-doctor --expect` pins. Each
snapshot's `CONTRACT_HASH` must equal the hash of `shared/`; `la-doctor --contract-hash` prints the bundled
one. Release only when every twin's version and contract hash agree.

## Dev and test commands

Python twin, in `python/`:

```bash
uv sync
uv run pytest -q                  # full suite, including the conformance corpus
uv run ruff check src tests
uv run basedpyright src tests
```

npm twin, in `node/` (the conformance runner is the Python one, so it needs `uv sync` in `python/`):

```bash
npm ci
npm run lint && npm run typecheck
npm test                          # Vitest, including the npm pack smoke test
npm run build && npm run conformance   # the corpus through the npm twin's bins
```

Repo-wide: `scripts/sync-shared [--check]`, `scripts/conformance-cross` (every case through both twins),
`la-arch-check` (this repo's own architecture, from either twin), and
`npx -y @anthropic-ai/claude-code plugin validate plugin`.

A language-specific command run through a twin that does not implement it natively forwards to the other
twin (found by `la-doctor --twin` on `PATH`, else `uvx`/`npx`); the npm twin forwards the Python-only
commands in this release.
