## 1. Tests (pr-tests stage; failing until implemented)

- [x] 1.1 Conformance runner (`python/tests/test_conformance.py`, `substitute`): `<MAJOR>` and `<MINOR>` (the
  installed version's first two components as written) are substituted wherever `<VERSION>` is (args, env, fake
  executables, git `write` content). Runner unit tests per place, like the existing `<FORMAT> <VERSION>` one;
  document both in `conformance/README.md`. Verify the unit tests fail before 2.x.
- [x] 1.2 Reword the `doctor.plugin-invalid` goldens (design.md decision 6) of `doctor-plugin-invalid-json`, `-nan`,
  `-bom`, `-invalid-utf8`, `-not-an-object`, `-no-version`, `-version-not-string`, `-lone-surrogate`; turn
  `doctor-plugin-surrogate-pair` (`😀`) into an invalid case (golden and note). Cases whose plugin is `<VERSION>`
  stay as they are.
- [x] 1.3 New cases (`golden: manual`, listed in `conformance/INVENTORY.md` under la-doctor):
  - healthy, exit 0: `doctor-plugin-same-series-other-patch` (`<MAJOR>.<MINOR>.999`),
    `doctor-plugin-same-series-prerelease` (`<MAJOR>.<MINOR>.0-rc1`), `doctor-plugin-same-series-leading-zeros`
    (`0<MAJOR>.0<MINOR>.7`), `doctor-plugin-huge-components` (`<MAJOR>` and `<MINOR>` each behind 400 leading
    zeros, so the digit strings exceed any float); plus the mismatch `doctor-plugin-huge-component-mismatch`
    (plugin `<MAJOR>.` + 400 nines + `.0`, normalized as below, exit 1);
  - invalid, exit 1: `doctor-plugin-version-two-components` (`0.4`), `-version-v-prefix` (`v0.4.1`),
    `-version-empty-rest` (`0.4.`), `-version-non-ascii-digit` (`٣.4.1`);
  - mismatch, twin-pinned, byte-exact: `doctor-plugin-mismatch-python` / `-typescript` (plugin `0.0.0` →
    `FAIL: installed la tools are <VERSION>, but plugin 0.0.0 needs 0.0.x; reinstall them with: uv tool install
    living-architecture==0.0.0`, resp. `npm install -g living-architecture@0.0.0`), and
    `doctor-plugin-mismatch-prerelease-python` / `-typescript` (plugin `0.0.0-rc1`);
  - mismatch, neutral (`normalize` pattern `(reinstall them with: ).*` → `\1<INSTALL>`, plus a pattern for any
    installed series in the output): `doctor-plugin-newer-minor` (`<MAJOR>.999.0`),
    `doctor-plugin-other-major` (`99<MAJOR>.<MINOR>.0`).
- [x] 1.4 Rewrite `doctor-plugin-mismatch` as the neutral, normalized `0.0.0` mismatch. Convert
  `doctor-format-missing-expect-mismatch` → `doctor-format-missing-plugin-mismatch` (`--plugin plugin`, plugin
  `0.0.1`, install normalized) and `doctor-all-problems-in-order` to `--plugin` (plugin `0.0.0`; its `contains` on
  `FAIL: installed la tools are` holds). Delete `doctor-expect-match`, `doctor-expect-mismatch`,
  `doctor-plugin-and-expect`, `doctor-usage-expect-without-value`; add `doctor-usage-expect-removed`
  (`--expect 0.4.1` → exit 2). Update `INVENTORY.md` rows (drop `--expect` wording).
- [x] 1.5 `shared/vectors/cli.yaml`: drop `expect` from every `la-doctor` `args`; the `flag and string options` vector
  becomes `argv: [--root, r, --contract-hash]`; add `argv: [--expect, 0.4.1]` → `exit: 2`. Verify
  `test_cli_parser.py` / `parser.test.ts` fail until 2.1.
- [x] 1.6 `python/tests/test_skills.py`: remove the `la-doctor --expect` assertion and its test.
- [x] 1.7 Doctor unit tests: `python/tests/test_doctor.py` drops `expect` (`run_checks(root=...)`, no `--expect` in
  `test_healthy`; delete `test_version_mismatch`/`test_no_expect_skips_version_check`); both twins get unit tests for
  the series comparison where conformance cannot reach (e.g. the installed version itself prerelease-style, via a
  patched version).
- [x] 1.8 Release rule (new `python/tests/test_release_scripts.py`; temp git repos mirroring the layout with tags,
  driving the copied `scripts/release-check` on the tagged commit): tool change → minor tag accepted; then an
  unchanged patch accepted; then a tool change → patch refused naming the previous tag and inputs; plugin/docs-only
  patch accepted; each tool-input kind counts (a file under each root, `node/scripts/`, `node/tsconfig.json`, a
  dependency in each manifest/lockfile) while a version-only manifest/lockfile change does not; changes in
  `plugin/`, `docs/`, `python/tests/` don't count; a major bump accepted; previous release chosen numerically
  (`v0.9.0` vs `v0.10.0`), non-`vX.Y.Z` tags (`v0.4.1-rc1`, `other`) and unreachable tags ignored; shallow clone,
  no reachable release tag, and HEAD ≠ tag commit (lightweight and annotated tags) each refused; the existing
  version-equality and contract-hash checks still fail on their own (one test each).
- [x] 1.9 `python/tests/test_versions.py`: a test applying the rule (through the `scripts/` module) to the repo's
  current version when no `v<current>` tag exists; skips without reachable release tags unless `GITHUB_ACTIONS` is
  set, then fails. Unit-test that gating with a temp repo (tag exists → not applied; no tags → skip / fail on
  Actions).
- [x] 1.10 npm packaging: `node/test/packaging.test.ts` packs a staged copy without `dist/` and without running
  `npm run build` first, and asserts the tarball carries `dist/bin/<command>.js` for every manifest command; drop the
  `package.test.ts` prepack-copy test (it runs `prepack` in a tree without sources).
- [x] 1.11 Codex review of the tests against this change (pr-tests Step 2); resolve findings with the user.

## 2. Implementation

- [ ] 2.1 `shared/cli.yaml`: remove `--expect` from `la-doctor`, reword the `--plugin` help (check the tools against
  its plugin.json version); `shared/findings.yaml`: the two approved wordings (design.md decisions 6–7) verbatim;
  run `scripts/sync-shared`. Verify 1.5 passes.
- [ ] 2.2 Python twin: `doctor` parses both versions by the spec's form, compares major/minor as canonical digit
  strings (design.md decision 10), drops `expect`/`_version_problem`; CLI drops `expect`. Verify `uv run pytest -q`
  doctor, parser and conformance tests pass.
- [ ] 2.3 npm twin: same in `node/src/doctor/index.ts` and the CLI; `prepack` runs `npm run build` then copies
  README/LICENSE. Verify 1.10 and `npm run build && npm run conformance`.
- [ ] 2.4 Release-rule module under `scripts/` (design.md decisions 9, 12); `scripts/release-check` calls it and adds
  the shallow / missing-release / HEAD-is-tag checks (decision 13). Verify 1.8 and 1.9.
- [ ] 2.5 `.github/workflows/ci.yml` and `publish.yml`: `fetch-depth: 0` on the checkouts that run tests or
  `release-check`. Verify by reading the workflows.

## 3. Docs

- [ ] 3.1 `AGENTS.md` "Versions and the contract hash": versions still move together; a release that changes the tool
  inputs raises the minor version, checked on the bump PR and by `scripts/release-check`; `la-doctor --plugin`
  compares major.minor.
- [ ] 3.2 `docs/development.md` "Releasing": choosing minor vs patch (what counts as a tool input), the PR-time
  check, and `release-check`'s new refusals.
- [ ] 3.3 `docs/commands.md` `la-doctor` row: "Check the installed tools' minor version matches the plugin, …".
- [ ] 3.4 README Install: one sentence that a plugin update within the same minor version needs no reinstall.

## 4. Verification

- [ ] 4.1 Python twin in `python/`: `uv run pytest -q`, `uv run ruff check src tests`, `uv run basedpyright src tests`.
- [ ] 4.2 npm twin in `node/`: `npm run lint && npm run typecheck`, `npm test`, `npm run build && npm run conformance`.
- [ ] 4.3 Repo-wide: `scripts/conformance-cross`, `scripts/sync-shared --check`, `la-arch-check` green,
  `npx -y @anthropic-ai/claude-code plugin validate plugin` with no new warning.
