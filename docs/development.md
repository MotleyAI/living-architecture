# Development

See [AGENTS.md](../AGENTS.md) for the rules of changing the contract, the twins and the conformance corpus, and
for the test commands.

## Working from a local checkout

To use and edit the plugins at the same time, run everything from a clone instead of a marketplace install:

```bash
git clone https://github.com/MotleyAI/living-architecture ~/src/living-architecture
cd ~/src/living-architecture
uv tool install -e python/la --with-editable python/trmv --with-executables-from type-rename-move
ln -s ~/src/living-architecture/plugin/trmv ~/.claude/skills/trmv
ln -s ~/src/living-architecture/plugin/la ~/.claude/skills/la
```

Claude Code loads a plugin directory under `~/.claude/skills/` in place (it shows as `la@skills-dir` in
`claude plugin list`), so this works in every launcher, including IDE and git-client integrations. The
alternative is `alias claude='claude --plugin-dir ~/src/living-architecture/plugin/trmv --plugin-dir
~/src/living-architecture/plugin/la'`, but launchers that don't read your shell aliases need those flags added to
their own command settings.

- Do **not** also install `trmv` or `la` from the marketplace: both copies would load and every skill would appear
  twice. If they are installed, run `/plugin uninstall la@living-architecture` and
  `/plugin uninstall trmv@living-architecture` first.
- Python edits take effect on the next command run (editable install). Edits under `shared/` (texts, schemas,
  the CLI manifests, the review scripts) take effect after `scripts/sync-shared`, which refreshes the vendored
  copies the commands load. Adding or renaming a command (in `shared/<package>/cli.yaml` and
  `python/<package>/pyproject.toml`) needs `uv tool install -e` again.
- SKILL.md edits take effect from the next Claude Code session.
- To try an unreleased checker in a repo that pins a release, `pip install -e <checkout>/python/trmv -e
  <checkout>/python/la` into that repo's environment; its next dependency sync restores the pin.

## Repository layout

| Path | Holds |
|---|---|
| `plugin/trmv/`, `plugin/la/` | the Claude Code plugins: `trmv`'s skills and per-language idioms, `la`'s skills; `la` depends on `trmv` |
| `python/trmv/`, `python/la/` | the PyPI twins (`type-rename-move`, `living-architecture`), one uv workspace with the dev-only conformance runner `python/conformance/`; `trmv-*` natively for Python, TypeScript inputs in the npm twin |
| `node/trmv/`, `node/la/` | the npm twins of the same names, one npm workspace; `trmv-*` natively for TypeScript, Python inputs in the PyPI twin |
| `shared/trmv/`, `shared/la/` | each package's contract: config and index schemas, finding texts, the CLI manifest, conventions and language registries, review scripts, test vectors |
| `conformance/trmv/`, `conformance/la/` | each package's byte-exact corpus pinning every command's observable output; `conformance/fixtures/` is shared |
| `architecture/` | this repo's own LikeC4 model and arc42 principles |
| `docs/` | the user documentation linked from the README; `docs/images/living-architecture.png` (the README image and the repo's social preview) is a headless-Chrome screenshot of its `.html` source at 1280×640 |
| `scripts/sync-shared` | vendors each package's `shared/<package>/` into both its twins |
| `scripts/conformance-cross` | runs every conformance case of both corpora through both twins' entry points |
| `scripts/release-check` | checks a release tag against every version, la's pins on trmv, trmv's plugin tag and each package's contract hashes |

`python/la/README.md` and both packages' `LICENSE` are symlinks to the root files (trmv has its own
`python/trmv/README.md`); `node/` copies them at pack time (`prepack`).

## CI shards

CI splits each PyPI twin's suite (`test`, two shards per Python version and package, conformance cases deselected)
and each `cross-twin` leg (three shards) with `pytest-split`, balanced by committed per-test durations in each
package: `python/<package>/tests/durations/suite.json`, `cross-python.json` and `cross-typescript.json`. Stale or
missing entries only unbalance the shards; every test still runs in exactly one. To refresh them, run each job kind
unsplit with `--store-durations --clean-durations`, ideally on a 4-vCPU runner like CI's:

```bash
for package in trmv la; do
  (cd python/$package && uv run pytest -q --store-durations --clean-durations \
    --durations-path tests/durations/suite.json --deselect tests/test_conformance.py::test_case)
done
scripts/conformance-cross --twin python --store-durations --clean-durations \
  --durations-path tests/durations/cross-python.json
scripts/conformance-cross --twin typescript --store-durations --clean-durations \
  --durations-path tests/durations/cross-typescript.json
```

## Releasing

Both packages and both plugins release together at one version. Bump it in `python/trmv` and `python/la` with
`uv version <new>`, in `node/trmv/package.json` and `node/la/package.json`, and in both
`plugin/<package>/.claude-plugin/plugin.json` (skills read them through `trmv-doctor --plugin` and
`la-doctor --plugin`); move la's pins on trmv to the new minor (`python/la/pyproject.toml`, `node/la/package.json`,
`plugin/la/.claude-plugin/plugin.json`'s `dependencies`); and update the pins in the README and the docs. The tests
fail until all agree. A release that changes the tool inputs since the previous release raises the minor (or major)
version; one that leaves them unchanged may raise only the patch, and needs no reinstall, since the doctors compare
only major.minor. The tool inputs are `shared/`, `conformance/`, `python/{trmv,la}/src/`, `node/{trmv,la}/src/`, the
npm build scripts (`node/scripts/`, `node/{trmv,la}/scripts/`), the npm tsconfigs, and the Python and npm manifests and
lockfiles beyond their own versions and la's pins. The rule lives in `scripts/release_rule.py`; the la suite applies
it to the bump PR while the new version has no tag (it skips without release tags locally, and fails without them on
GitHub Actions). A release that changes a config file's format appends its own version to that file's series under
`formats` in `shared/trmv/config.yaml`; for `living-architecture.yaml` (or anything under `architecture/`) it also
adds, in both twins, the `la-arch-migrate` step from the previous format. The tests check that every older format
has a step, and `scripts/release-check` that the release appended exactly its own version to each series. Tag
`trmv--v<version>` with `claude plugin tag --push` from `plugin/trmv` (the tag la's plugin dependency on trmv resolves
against), then tag `v<version>` and publish a GitHub release for it; the `Publish` workflow first runs
`scripts/release-check` (HEAD is the tag's commit, every version equals the tag, la pins trmv to its minor,
`trmv--v<version>` is at the same commit, each snapshot records its contract's hash, and the release rule holds against
the highest reachable `vX.Y.Z` tag below it; it also refuses a shallow clone or no reachable previous release) and publishes no twin otherwise. It publishes `type-rename-move` before
`living-architecture` on PyPI and on npm, skipping an npm package whose `package.json` is `"private": true`, and
on a rerun every distribution already published, so a rerun finishes a partial release. npm
publishes through trusted publishing, which trusts `publish.yml` in this repository by name: renaming the workflow
needs a new trusted publisher in each package's npmjs.com settings.
