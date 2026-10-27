## 1. Tests (pr-tests stage; failing until implemented)

- [ ] 1.1 Conformance runner (`python/tests/test_conformance.py`): `<TOOLS_FINGERPRINT>` is substituted wherever
  `<VERSION>` is (args, env, git `write` content; see `_substitute` near line 204) with the committed
  `plugin/.claude-plugin/TOOLS_FINGERPRINT` value (stripped of its newline). Runner unit tests per place, like the
  existing `<FORMAT> <VERSION>` one; document the placeholder in `conformance/README.md`. Verify the unit tests fail
  before 2.x.
- [ ] 1.2 Update the `--plugin` cases that reach the fingerprint step to write
  `plugin/.claude-plugin/TOOLS_FINGERPRINT: "<TOOLS_FINGERPRINT>\n"`: `doctor-plugin-match`, `-relative-dir`,
  `-dangling-link`, `-surrogate-pair` (now healthy, exit 0: the escaped pair is a valid version). The
  manifest-error cases (`-bom`, `-invalid-json`, `-lone-surrogate`, `-nan`, `-not-an-object`, `-no-version`,
  `-version-not-string`, `-unreadable`, `-not-found`, `-double-slash`) stay as they are.
- [ ] 1.3 New cases (`golden: manual`, listed in `conformance/INVENTORY.md` under la-doctor):
  - `doctor-plugin-versions-differ-tools-same`: `plugin.json` `0.0.0` + matching fingerprint → `ok`, exit 0.
  - `doctor-plugin-tools-mismatch-python` / `-typescript` (`twin:` pinned): a well-formed foreign fingerprint, plugin
    `0.0.0` → `FAIL: installed la tools are <VERSION>, not the tools plugin 0.0.0 was released with; reinstall them
    with: uv tool install living-architecture==0.0.0` (resp. `npm install -g living-architecture@0.0.0`), exit 1.
  - `doctor-plugin-tools-mismatch-same-version-python` / `-typescript` (`twin:` pinned): plugin `<VERSION>` + foreign
    fingerprint → the same finding naming `<VERSION>` twice, exit 1.
  - `doctor-plugin-fingerprint-missing`: valid `plugin.json`, no `TOOLS_FINGERPRINT` → `doctor.tools-mismatch`
    (neutral: `normalize` pattern `(reinstall them with: ).*` → `\1<INSTALL>`), exit 1.
  - `doctor-plugin-fingerprint-dangling-link`: `TOOLS_FINGERPRINT` a dangling symlink → mismatch (same
    normalization), exit 1.
  - `doctor-plugin-fingerprint-directory`: `TOOLS_FINGERPRINT/x` written (a directory) →
    `FAIL: cannot inspect <ROOT>/repo/plugin/.claude-plugin/TOOLS_FINGERPRINT`, exit 1.
  - `doctor-plugin-fingerprint-invalid-{uppercase,short,crlf,trailing-space,two-newlines}` → `FAIL: <path> does not
    hold a tools fingerprint (64 lowercase hex digits)`, exit 1; plus `doctor-plugin-fingerprint-no-newline` (64 hex,
    no `\n`) → healthy.
  - `doctor-plugin-invalid-with-fingerprint`: invalid `plugin.json` + valid fingerprint → only `doctor.plugin-invalid`.
- [ ] 1.4 Convert `doctor-format-missing-expect-mismatch` → `doctor-format-missing-plugin-mismatch` (`--plugin plugin`,
  plugin `0.0.1` without fingerprint, install command normalized as in 1.3) and `doctor-all-problems-in-order` to
  `--plugin` (its `contains` on `FAIL: installed la tools are` holds). Delete `doctor-expect-match`,
  `doctor-expect-mismatch`, `doctor-plugin-and-expect`, `doctor-usage-expect-without-value`; add
  `doctor-usage-expect-removed` (`--expect 0.4.1` → exit 2). Rewrite `doctor-plugin-mismatch` as the neutral,
  normalized mismatch of a foreign fingerprint. Update `INVENTORY.md` rows (drop `--expect` wording).
- [ ] 1.5 `shared/vectors/cli.yaml`: drop `expect` from every `la-doctor` `args`; the `flag and string options` vector
  becomes `[--contract-hash, --root, r]`-style without `--expect`; add a vector `argv: [--expect, 0.4.1]` → `exit: 2`.
  Verify `test_vectors.py` / `vectors.test.ts` fail until 2.1.
- [ ] 1.6 `python/tests/test_skills.py`: remove the `la-doctor --expect` assertion (line ~67) and its scenario's test.
- [ ] 1.7 Drift tests: `python/tests/test_versions.py` and `node/test/package.test.ts` assert the three
  `TOOLS_FINGERPRINT` files are byte-identical and match `^[0-9a-f]{64}\n$`.
- [ ] 1.8 Packaging: `python/tests/test_packaging.py` installs the wheel outside the checkout and runs
  `la-doctor --plugin <tmp plugin>` with the source fingerprint and `plugin.json` `0.0.0` → exit 0, and the wheel
  contains `living_architecture/TOOLS_FINGERPRINT` with the source bytes. `node/test/packaging.test.ts` does the same
  for the packed tarball (`package/dist/TOOLS_FINGERPRINT`), and a new test packs from a tree with `dist/` deleted and
  finds `dist/` in the tarball (the `prepack` build).
- [ ] 1.9 `python/tests/test_doctor.py` / `node/test/doctor.test.ts`: unit tests for whatever the conformance cases
  cannot reach (an `EACCES` fingerprint file → `doctor.plugin-unreadable`; the twin's own bundled fingerprint is read
  from the package).
- [ ] 1.10 Fingerprint module tests (new `python/tests/test_release_scripts.py`, temp git repos): the value is the
  sha256 over (path, git mode, length, blob) sorted by UTF-8 path bytes, from HEAD; excludes the twins'
  `TOOLS_FINGERPRINT`; ignores untracked and ignored files; equal across checkouts with `core.autocrlf=true` + a
  `* text=auto` attribute, `core.filemode=false` and `core.symlinks=false`; an executable bit and a symlink each change
  it.
- [ ] 1.11 `scripts/release-bump` tests (same file; temp git repo mirroring the layout, fake `uv`/`npm` on `PATH`
  that record their argv and edit the files like the real tools): `0.9.9 → 0.10.0` accepted; `0.4.1-rc1`, `1.2`,
  equal and lower versions refused; a dirty tracked covered file and an untracked non-ignored one refused, an ignored
  one fine; stale snapshots refused; a doc pin not naming the current version refused; unrelated package names
  untouched; every refusal leaves every file byte-identical; a success sets `plugin.json`, calls `uv version <v>` in
  `python/` and `npm version <v> --no-git-tag-version` in `node/`, rewrites README/`docs/*.md` pins, writes the three
  fingerprint files, prints each changed file and "tools changed"/"tools unchanged"; a forced failure after each phase
  (fake `uv`/`npm` exiting 1, an unwritable target) exits 1 and restores every touched file.
- [ ] 1.12 `scripts/release-check` tests: a stale fingerprint in any of the three files fails naming each; current
  ones pass alongside the existing version/hash checks.
- [ ] 1.13 Codex review of the tests against this change (pr-tests Step 2); resolve findings with the user.

## 2. Implementation

- [ ] 2.1 `shared/cli.yaml`: remove `--expect` from `la-doctor`; `shared/findings.yaml`: remove
  `doctor.version-mismatch`, add `doctor.tools-mismatch` and `doctor.plugin-fingerprint-invalid` with the approved
  wordings (design.md decisions 5–6) verbatim; run `scripts/sync-shared`. Verify 1.5 passes.
- [ ] 2.2 `scripts/` fingerprint module (git `ls-tree` + `cat-file --batch`, design.md decision 9); verify 1.10.
- [ ] 2.3 `scripts/release-bump` (design.md decisions 2, 10, 17–19); verify 1.11.
- [ ] 2.4 `scripts/release-check`: add the fingerprint check; verify 1.12.
- [ ] 2.5 Stamp the three `TOOLS_FINGERPRINT` files with the fingerprint of HEAD (committed implementation), via the
  module; verify 1.7. Re-stamp after the last commit touching a covered path, before the PR is opened.
- [ ] 2.6 Python twin: read `living_architecture/TOOLS_FINGERPRINT` beside `__version__`; `doctor` compares it with
  the plugin's per the spec, drops `expect`/`_version_problem`; CLI drops `expect`. Verify `uv run pytest -q`
  doctor, vectors and conformance tests pass.
- [ ] 2.7 npm twin: same in `node/src/index.ts` and `node/src/doctor/index.ts`; `build.mjs` copies
  `src/TOOLS_FINGERPRINT` to `dist/`; `prepack` runs `npm run build` then copies README/LICENSE. Verify 1.8 and
  `npm run build && npm run conformance`.

## 3. Docs

- [ ] 3.1 `AGENTS.md` "Versions and the contract hash": versions still move together; `TOOLS_FINGERPRINT` (plugin and
  both twins) is stamped by `scripts/release-bump` and verified by `scripts/release-check`; `la-doctor --plugin`
  compares it, not the version.
- [ ] 3.2 `docs/development.md` "Releasing": run `scripts/release-bump <version>` (plus the existing `format` note),
  commit, tag, publish; drop the manual three-file bump and pin edits.
- [ ] 3.3 `docs/commands.md` `la-doctor` row: "Check the installed tools match the plugin, …".
- [ ] 3.4 README Install: one sentence that a plugin update leaving the commands unchanged needs no reinstall.

## 4. Verification

- [ ] 4.1 Python twin in `python/`: `uv run pytest -q`, `uv run ruff check src tests`, `uv run basedpyright src tests`.
- [ ] 4.2 npm twin in `node/`: `npm run lint && npm run typecheck`, `npm test`, `npm run build && npm run conformance`.
- [ ] 4.3 Repo-wide: `scripts/conformance-cross`, `scripts/sync-shared --check`, `scripts/release-check v<current>`
  green, `la-arch-check` green, `npx -y @anthropic-ai/claude-code plugin validate plugin` with no new warning.
