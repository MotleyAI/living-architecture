## Context

Each package is built from its own folder. `uv build` runs in `python/`; `pyproject.toml` has
`readme = "README.md"` and `license-files = ["LICENSE"]`, `uv_build` reads neither from outside `python/`
(`readme = "../README.md"` is unsupported) and runs no build hooks. `npm publish` runs in `node/` and packs only
`files` (`dist`, `README.md`, `LICENSE`). Verified during triage at 0.4.0: `uv build` follows symlinks (the sdist
holds the real files, the wheel `METADATA` the full README); `npm pack` drops symlinked files (npm 10.9.8 and
11.21.1).

## Goals / Non-Goals

**Goals:** no committed copy of the root `README.md`/`LICENSE` anywhere, so no drift is possible; both published
packages still carry both files byte-for-byte.

**Non-Goals:** a release or version bump; any workflow change; Windows symlink support.

## Decisions

- **Symlinks in `python/`**, committed as git symlinks (mode 120000). `uv_build` follows them, and a fresh clone's
  `uv sync` (which builds the project) needs no extra step.
- **`prepack` copy in `node/`**, gitignored. The script is an inline node one-liner,
  `node -e "for (const f of ['README.md', 'LICENSE']) require('node:fs').copyFileSync('../' + f, f)"`, rather than
  `cp` (npm runs scripts under `cmd.exe` on Windows) or a separate `scripts/*.mjs` file (a file just to copy two
  files). npm runs `prepack` on both `npm pack` and `npm publish`, so the pack smoke test and `publish.yml` see the
  same tarball.
- **`scripts/sync-shared` drops README/LICENSE entirely** (`VENDORED`, its staleness check and copy loop). Kept, it
  would also break: `shutil.copy2` onto a symlink to the same file raises `SameFileError`.
- **Rejected: Hatchling with a pre-build copy hook**: a new backend and a hook script to copy two files a symlink
  already handles.
- **Rejected: copying only in `publish.yml`, gitignored on both sides**: `uv sync` in `python/` builds the project,
  so a fresh clone would fail until someone ran the copy.
- **Tests pin outcomes, not text.** The tarball, sdist and wheel contents are compared to the root bytes (wheel:
  `METADATA` description and `dist-info/licenses/LICENSE`); `prepack` is run in a temp root; gitignore status is
  checked per path with `git check-ignore --no-index -q`. The pack test deletes `node/README.md`/`node/LICENSE`
  before packing so leftovers from an earlier pack cannot mask a broken `prepack`. The `sync-shared` fixture mirrors
  the real layout (root files, `python/` symlinks, no `node/` copies) and a test asserts sync leaves it untouched.

## Risks / Trade-offs

- [A Windows checkout without symlink support writes `python/README.md` as a text file holding the link path, so a
  local Windows build would publish a broken README] → releases are built on Linux CI.
- [The pack smoke test writes `node/README.md`/`node/LICENSE` into the checkout through `prepack`] → both are
  gitignored build outputs, like the `node/dist/` that test already builds there; only that test packs.
