## Why

`scripts/sync-shared` copies the root `README.md` and `LICENSE` into `python/` and `node/`, and the copies are
committed and pinned by drift tests. Every README edit therefore needs a sync run, and an edit made in GitHub's web
editor always turns CI red (PR #23: every Python job and the node job).

## What Changes

- `python/README.md` and `python/LICENSE` become relative symlinks to the root files; `uv build` follows them, so
  the sdist and wheel carry the real files.
- `node/` stops committing its copies: a `prepack` script copies `../README.md` and `../LICENSE` into `node/` on
  `npm pack` and `npm publish`, and both paths are gitignored. `files` is unchanged.
- `scripts/sync-shared` vendors only `shared/` into the two contract snapshots, no longer `README.md`/`LICENSE`.
- The README/LICENSE drift tests go; tests pin the symlinks, the built sdist/wheel and the packed tarball contents,
  the `prepack` copy, and the gitignore entries.
- `AGENTS.md` and `docs/development.md` describe the new arrangement.

## Capabilities

### New Capabilities

### Modified Capabilities

None: packaging and tooling only, no command behaviour changes (`skip_specs: true`).

## Impact

- `python/README.md`, `python/LICENSE` (symlinks), `node/package.json` (`prepack`), `.gitignore`,
  `node/README.md`/`node/LICENSE` (removed from git), `scripts/sync-shared`.
- Tests: `python/tests/test_versions.py`, `test_sync_shared.py`, `test_packaging.py`, `test_scrub.py`;
  `node/test/package.test.ts`, `node/test/packaging.test.ts`.
- Docs: `AGENTS.md`, `docs/development.md`.
- No workflow change: `publish.yml`'s `npm publish` runs `prepack`, `uv build` follows the symlinks.
- A Windows checkout without symlink support gets `python/README.md` as a link-path text file; releases build on
  Linux CI.
