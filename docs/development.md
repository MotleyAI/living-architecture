# Development

See [AGENTS.md](../AGENTS.md) for the rules of changing the contract, the twins and the conformance corpus, and
for the test commands.

## Working from a local checkout

To use and edit the plugin at the same time, run everything from a clone instead of a marketplace install:

```bash
git clone https://github.com/MotleyAI/living-architecture ~/src/living-architecture
uv tool install -e ~/src/living-architecture/python
ln -s ~/src/living-architecture/plugin ~/.claude/skills/la
```

Claude Code loads a plugin directory under `~/.claude/skills/` in place (it shows as `la@skills-dir` in
`claude plugin list`), so this works in every launcher, including IDE and git-client integrations. The
alternative is `alias claude='claude --plugin-dir ~/src/living-architecture/plugin'`, but launchers that don't
read your shell aliases need that flag added to their own command settings.

- Do **not** also install `la` from the marketplace: both copies would load and every skill would appear twice.
  If it is installed, run `/plugin uninstall la@living-architecture` first.
- Python edits take effect on the next command run (editable install). Edits under `shared/` (texts, schemas,
  the CLI manifest, the review scripts) take effect after `scripts/sync-shared`, which refreshes the vendored
  copy the commands load. Adding or renaming a command (in `shared/cli.yaml` and `python/pyproject.toml`) needs
  `uv tool install -e` again.
- SKILL.md edits take effect from the next Claude Code session.
- To try an unreleased checker in a repo that pins a release, `pip install -e <checkout>/python` into that
  repo's environment; its next dependency sync restores the pin.

## Repository layout

| Path | Holds |
|---|---|
| `plugin/` | the Claude Code plugin: skills |
| `python/` | the PyPI twin (`living-architecture`): every `la-*`/`dr-*` command |
| `node/` | the npm twin (`living-architecture`): the language-neutral commands and the TypeScript arch-check, conventions and type check; forwards the Python-only `dr-*` commands |
| `shared/` | the contract the commands obey: config and index schemas, finding texts, the CLI manifest, conventions and language registries, review scripts, test vectors |
| `conformance/` | the byte-exact corpus pinning every command's observable output |
| `architecture/` | this repo's own LikeC4 model and arc42 principles |
| `docs/` | the user documentation linked from the README |
| `scripts/sync-shared` | vendors `shared/`, `README.md` and `LICENSE` into both twins |
| `scripts/conformance-cross` | runs every conformance case through both twins' entry points |
| `scripts/release-check` | checks a release tag against both twins' versions and contract hashes |

## Releasing

In `python/`, bump the version with `uv version <new>`, then in `node/package.json`,
`plugin/.claude-plugin/plugin.json` and every skill's `la-doctor --expect` pin (the tests fail until all agree),
and update the pins in the README and [commands.md](commands.md). Run `scripts/sync-shared` and commit the
refreshed copies. Tag `v<version>` and publish a GitHub release for it; the `Publish` workflow first runs
`scripts/release-check` (every version equals the tag, both contract hashes agree) and publishes neither twin
otherwise. The npm job skips while `node/package.json` is `"private": true`.
