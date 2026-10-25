## 1. Tests (pr-tests stage; failing until implemented)

- [ ] 1.1 `python/tests/test_versions.py`: remove `test_vendored_root_files_are_current` and
  `test_npm_vendored_root_files_are_current`; add a test that `python/README.md` and `python/LICENSE` are symlinks
  whose `resolve()` is the root `README.md` / `LICENSE`. Verify it fails before 2.1.
- [ ] 1.2 `python/tests/test_sync_shared.py`: remove `test_sync_vendors_the_root_files`; the `tree` fixture mirrors
  the real layout (root `README.md`/`LICENSE`, `python/README.md`/`python/LICENSE` as relative symlinks to them, no
  `node/` copies) instead of copying the twin files. New test: `--check` passes, and a normal sync leaves both
  `python/` paths symlinks resolving to the root files, creates no `node/README.md`/`node/LICENSE`, and leaves the
  root files' bytes unchanged. Verify it fails against the current script.
- [ ] 1.3 `python/tests/test_packaging.py` (module-scoped `artifacts` fixture): the sdist contains `README.md` and
  `LICENSE` with the root files' bytes; the wheel `METADATA` description (body after the header block) equals the
  root README; the wheel's `*.dist-info/licenses/LICENSE` equals the root LICENSE byte-for-byte.
- [ ] 1.4 `python/tests/test_scrub.py`: `README_COPIES = ("README.md", "python/README.md")`, so
  `test_file_exemptions_hold_only_in_their_own_file` holds once `node/README.md` is ignored. Verify the scrub tests
  pass after 2.2.
- [ ] 1.5 `node/test/package.test.ts`: remove the `vendored files › %s equals the root copy` test and drop "vendored
  root files" from the header comment. Add: `scripts.prepack`, run with `npm run prepack` in a temp root holding
  `README.md`, `LICENSE` and a `node/` with a copy of `package.json`, leaves byte-equal copies of both files in that
  `node/`; per path, `git check-ignore --no-index -q` exits 0 for `node/README.md` and `node/LICENSE` and 1 for
  `python/README.md` and `python/LICENSE`. Verify both fail before 2.2.
- [ ] 1.6 `node/test/packaging.test.ts`: `beforeAll` deletes `node/README.md`/`node/LICENSE` (`force`) before
  `npm pack`, so leftovers cannot mask a broken `prepack`; a test extracts the packed tarball under TMP and asserts
  `package/README.md` and `package/LICENSE` equal the root files' bytes.
- [ ] 1.7 Codex review of the tests against this change (pr-tests Step 2); resolve findings with the user.

## 2. Implementation

- [ ] 2.1 `python/`: replace `README.md` and `LICENSE` with `ln -s ../README.md` / `ln -s ../LICENSE`;
  `git ls-files -s python/README.md python/LICENSE` shows mode 120000. `pyproject.toml` unchanged. Verify 1.1 and
  1.3 pass.
- [ ] 2.2 `node/`: add `"prepack": "node -e \"for (const f of ['README.md', 'LICENSE']) require('node:fs').copyFileSync('../' + f, f)\""`
  to `package.json` (`files` unchanged); `git rm --cached node/README.md node/LICENSE`; add `/node/README.md` and
  `/node/LICENSE` to the root `.gitignore`. Verify 1.5 and 1.6 pass.
- [ ] 2.3 `scripts/sync-shared`: drop `VENDORED`, its `--check` staleness entries and its copy loop; the docstring
  loses ", plus README.md and LICENSE". Verify 1.2 passes and `scripts/sync-shared --check` exits 0.

## 3. Docs

- [ ] 3.1 `AGENTS.md` step 2: drop " (and the vendored `README.md`/`LICENSE`)".
- [ ] 3.2 `docs/development.md`: the `scripts/sync-shared` layout row becomes "vendors `shared/` into both twins";
  one sentence near the layout table that `python/README.md` and `python/LICENSE` are symlinks to the root files and
  `node/` copies them at pack time (`prepack`).

## 4. Verification

- [ ] 4.1 Python twin in `python/`: `uv run pytest -q`, `uv run ruff check src tests`, `uv run basedpyright src tests`
  all green.
- [ ] 4.2 npm twin in `node/`: `npm run lint && npm run typecheck`, `npm test` (incl. the pack smoke test),
  `npm run build && npm run conformance` all green.
- [ ] 4.3 Repo-wide: `scripts/conformance-cross` and `scripts/sync-shared --check` green; `git status` shows no
  `node/README.md`/`node/LICENSE` after the pack test.
