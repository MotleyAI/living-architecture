# Working in this repo

## The twin rule

The `la-*`/`dr-*` commands have one contract and one implementation per ecosystem: the PyPI package in
`python/` (Python target repos) and, from the next release line, an npm package in `node/` (TS/JS target
repos). Every behaviour observable through a command must be identical in both twins for the languages they
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

The case format is in `conformance/README.md`.

## Goldens

Write goldens only with `LA_UPDATE_GOLDENS=1`, and only with a stated reason in the commit message (a
deliberate behaviour change, or a new case). Review the golden diff like code. Never regenerate a golden to
absorb a difference you cannot explain. Cases marked `golden: manual` pin new behaviour and are edited by
hand.

## Versions and the contract hash

The package versions (`python/pyproject.toml`, and `node/package.json` once it exists) and
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

Repo-wide: `scripts/sync-shared [--check]`, `la-arch-check` (this repo's own architecture), and
`npx -y @anthropic-ai/claude-code plugin validate plugin`.
