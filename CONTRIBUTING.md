# Contributing to living-architecture

Bug reports, questions and pull requests are welcome.

## Reporting a problem

Open an [issue](https://github.com/MotleyAI/living-architecture/issues/new/choose). For a wrong finding or a
crash, include the command you ran, its full output, the installed version (`la-doctor` prints it) and, if you
can, a minimal repo or `architecture/` folder that reproduces it. Report security problems privately, as
described in [SECURITY.md](SECURITY.md).

## Setting up

```bash
git clone https://github.com/MotleyAI/living-architecture
cd living-architecture/python && uv sync && uv run pytest -q
cd ../node && npm ci && npm test
```

[docs/development.md](docs/development.md) shows how to run the plugin and the commands from your checkout, and
the repository layout.

## How changes are made

This repo is developed with its own plugin: each change goes through `/la:pr` on a branch named after its
issue, and the review loop runs CI, Codex, CodeRabbit and Sonar. You don't need the plugin to contribute, but a
PR has to pass CI, and the CodeRabbit and Sonar reviews when they run on it. If you lack the repo's tracker
(Linear) or Codex, override them for yourself in a git-ignored `living-architecture.local.yaml`
([details](docs/configuration.md#local-overrides)).

The rules that matter most are in [AGENTS.md](AGENTS.md):

- **One contract, two implementations.** Every command exists in a Python package (`python/`) and an npm package
  (`node/`) that must behave identically. Parameters, defaults and user-facing texts live only in `shared/`; run
  `scripts/sync-shared` after editing it.
- **The conformance corpus decides.** Each behaviour is pinned by a case under `conformance/cases/`. A twin
  whose output differs from a golden is wrong, not the golden. Regenerate goldens only for a deliberate change,
  and say why in the commit message.
- **The architecture is checked.** `architecture/` holds this repo's own model and principles. `la-arch-check`
  must pass, and changes to the model or the principles need a maintainer's approval, like changes to tests.

## Pull requests

Keep one change per PR, with tests for it in both twins where it applies. Before you push, run the full suites
and the checks from [AGENTS.md](AGENTS.md#dev-and-test-commands).
