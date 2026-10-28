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
| `python/` | the PyPI twin (`living-architecture`): every `la-*`/`dr-*` command; `dr-*` natively for Python, TypeScript inputs in the npm twin |
| `node/` | the npm twin (`living-architecture`): every `la-*`/`dr-*` command; `dr-*` natively for TypeScript, Python inputs in the PyPI twin |
| `shared/` | the contract the commands obey: config and index schemas, finding texts, the CLI manifest, conventions and language registries, review scripts, test vectors |
| `conformance/` | the byte-exact corpus pinning every command's observable output |
| `architecture/` | this repo's own LikeC4 model and arc42 principles |
| `docs/` | the user documentation linked from the README; `docs/images/living-architecture.png` (the README image and the repo's social preview) is a headless-Chrome screenshot of its `.html` source at 1280×640 |
| `scripts/sync-shared` | vendors `shared/` into both twins |
| `scripts/conformance-cross` | runs every conformance case through both twins' entry points |
| `scripts/release-check` | checks a release tag against both twins' versions and contract hashes |

`python/README.md` and `python/LICENSE` are symlinks to the root files; `node/` copies them at pack time
(`prepack`).

## Releasing

In `python/`, bump the version with `uv version <new>`, then in `node/package.json` and
`plugin/.claude-plugin/plugin.json` (skills read it through `la-doctor --plugin`; the tests fail until all agree),
and update the pins in the README and [commands.md](commands.md). A release that changes the tool inputs since the
previous release raises the minor (or major) version; one that leaves them unchanged may raise only the patch, and
needs no reinstall, since `la-doctor --plugin` compares only major.minor. The tool inputs are `shared/`,
`conformance/`, `python/src/`, `node/src/`, `node/scripts/`, `node/tsconfig*.json`, and `python/pyproject.toml`,
`python/uv.lock`, `node/package.json` and `node/package-lock.json` beyond their own version. The rule lives in
`scripts/release_rule.py`; the Python suite applies it to the bump PR while the new version has no tag (it skips
without release tags locally, and fails without them on GitHub Actions). A release that changes the repo format
(`living-architecture.yaml` or anything under `architecture/`) also sets `format` in `shared/config.yaml` to its
own version and adds the conversion to `la-arch-migrate`. Tag `v<version>` and publish a GitHub release for it;
the `Publish` workflow first runs `scripts/release-check` (HEAD is the tag's commit, every version equals the
tag, both contract hashes agree, and the release rule holds against the highest reachable `vX.Y.Z` tag below it; it
also refuses a shallow clone or no reachable previous release) and publishes neither twin otherwise. The npm job skips while `node/package.json` is `"private": true`. It
publishes through npm trusted publishing, which trusts `publish.yml` in this repository by name: renaming the
workflow needs a new trusted publisher in the package's npmjs.com settings.
