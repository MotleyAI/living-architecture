## Context

Users install the plugin from the marketplace (`.claude-plugin/marketplace.json`, source `./plugin`, no ref), so
new installs and updates take `plugin/` from main's HEAD, not from a tag. Main's `plugin.json` names the last
release until the next bump. The twins read their versions from package metadata (`importlib.metadata`,
`package.json`), so nothing under `shared/`, `conformance/`, `python/src/` or `node/src/` changes at a release
unless the tools do (verified for v0.4.0 → v0.4.1). `CONTRACT_HASH` (written by `scripts/sync-shared`) answers
"do the twins speak the same contract?"; the fingerprint answers "are these the tools the plugin was released
with?".

Architecture: touched elements are `python.doctor` / `typescript.doctor`, the root package
(`living_architecture/__init__.py`, `node/src/index.ts`, which already expose the version) and `shared/` through
`contract`. System principles 1 (twins identical, conformance decides) and 2 (texts and flags only from `shared/`)
apply; 3 and 4 do not. No arc42 or model edit. The spec attaches to the cross-cutting `shared-contract` capability.

## Goals / Non-Goals

**Goals:** a release that leaves the tools unchanged needs no reinstall; any tool change still forces one; main's
plugin always names tools that can be installed.

**Non-Goals:**
- The twin handshake (`la-doctor --twin`, facts `contract_hash`/`version`) stays version + contract hash:
  forwarding pins the other twin to its own version, so it is unaffected.
- No `la-doctor --tools-fingerprint` print flag: nothing needs it.
- The `format` bump in `shared/config.yaml` stays a manual release step.
- Dependency manifests, `node/scripts/build.mjs` and packaging config are not fingerprinted.

## Decisions

1. **Stamp at release, not on every sync.** Options: (a) `sync-shared` restamps on every run, drift test requires
   the current fingerprint; (b) stamp at the release bump, drift test requires only that the three copies agree,
   `release-check` requires them current. Taken: (b). Under (a) main's plugin would carry unreleased tools'
   fingerprint, so a marketplace install between a tools-changing merge and the release fails `la-doctor` with
   advice that cannot fix it; (a) also forces a sync on every source PR and makes concurrent PRs conflict on three
   files. Cost of (b): a dev install from a checkout reports the last release's fingerprint, the same blind spot the
   version has today. (user)
2. **A new `scripts/release-bump <version>` does the whole bump**, versions, lockfiles, doc pins and fingerprint,
   rather than `scripts/sync-shared --stamp` beside a manual bump. The fingerprint is release identity like the
   version, so they move in one command; `sync-shared` keeps one job (vendoring `shared/`). (user)
3. **Plugin storage: `plugin/.claude-plugin/TOOLS_FINGERPRINT`**, rather than a `toolsFingerprint` key in
   `plugin.json`, which `plugin validate` warns about ("Unknown field 'toolsFingerprint'. Claude Code ignores it at
   load time."). Mirrors `CONTRACT_HASH`; costs one more file read and two findings. (user)
4. **`--expect` is removed** rather than repurposed to take a fingerprint: no caller in `plugin/`, docs or README,
   and it encoded the exact version-equality rule this change drops; keeping it would leave two checks that
   disagree. (user)
5. **The mismatch finding names the invoking twin's own install command** (its language's `install` template at
   the plugin's version), rather than both ecosystems' commands. Its cases are pinned per twin, like
   `doctor-twin-identity-*`. Wording: `doctor.tools-mismatch: 'installed la tools are {installed}, not the tools
   plugin {expected} was released with; reinstall them with: {install}'` (user, approved wording)
6. **Malformed-fingerprint wording:** `doctor.plugin-fingerprint-invalid: '{path} does not hold a tools fingerprint
   (64 lowercase hex digits)'` (user, approved wording)
7. **Twins' storage:** `TOOLS_FINGERPRINT` beside each root package (`python/src/living_architecture/`,
   `node/src/`, copied to `dist/` by `build.mjs`), read where the version is read. (default)
8. **Coverage is exactly the issue's set** (`shared/`, `conformance/`, `python/src/`, `node/src/`, minus the twins'
   `TOOLS_FINGERPRINT`): a dependency or build-config bump does not change what the skills need from the commands.
   (default)
9. **Hash over git objects at HEAD**: `git ls-tree -r -z HEAD -- <roots>`, then sha256 over (path, git mode, length,
   blob bytes via `git cat-file --batch`) per entry, paths sorted by UTF-8 bytes, the same tuple shape as
   `CONTRACT_HASH`. Hashing the working tree with `stat()` would depend on `core.autocrlf`/attributes,
   `core.filemode` and `core.symlinks`, so a local `release-bump` and CI's `release-check` could disagree; HEAD is
   exactly what gets tagged. A symlink contributes mode `120000` and its target blob. (codex)
10. **`release-bump` refuses on a dirty covered tree** (uncommitted changes or untracked non-ignored files under the
    roots), so uncommitted tools cannot be released under a HEAD fingerprint. (default)
11. **One definition**: a fingerprint module under `scripts/`, imported by `release-bump` and `release-check`; the
    twins never compute it. (default)
12. **Missing plugin fingerprint is a mismatch, not invalid**: a plugin released before this change then gets the
    correct advice (reinstall the tools at that plugin's version). (default)
13. **Validity is the exact bytes `^[0-9a-f]{64}\n?$`, no trimming**, so Python's `strip` and JS's `trim` cannot
    diverge. (default)
14. **A fingerprint path that exists but cannot be read reuses `doctor.plugin-unreadable`.** (default)
15. **The "Skill pins a version" scenario and its skills-test check go with the flag**; a skill passing `--expect`
    now gets a usage error. (default)
16. **README gets one sentence under Install** that a plugin update leaving the commands unchanged needs no
    reinstall: a small docs extension beyond `AGENTS.md` and `development.md`. (default)
17. **`release-bump` uses `uv version` and `npm version --no-git-tag-version`** rather than text edits, so
    `uv.lock` and `package-lock.json` stay consistent. (default)
18. **`release-bump` is all or nothing**: it snapshots every file it may touch and restores them all if any step
    fails. (codex)
19. **Doc pins**: `release-bump` reuses the one pin regex of `test_doc_pins_name_the_current_version`, refuses when
    any pin differs from the current version, and only then rewrites them all. (codex)
20. **`release-bump` test plan**: temp git repo, fake `uv`/`npm` on `PATH`; numeric ordering (0.9.9 → 0.10.0);
    malformed, prerelease, equal and lower versions refused; dirty tracked, untracked non-ignored (refused) and
    ignored (fine) files; stale snapshots; tools changed/unchanged report; every written file; refusals leave every
    file byte-identical; forced failure after each phase restores everything. (codex)
21. **Packaging is proven by running the packaged twin**: the wheel and `npm pack` smoke tests install outside the
    checkout and run `la-doctor --plugin` against a plugin holding the source fingerprint, expecting healthy. No
    explicit `uv_build` include: `uv_build` ships every file under the module tree, which the contract data already
    relies on. (codex; the explicit include rejected)
22. **`prepack` runs `npm run build`** before copying README/LICENSE, with a test that packs from a tree without
    `dist/`: a direct `npm pack` shipped a stale or missing `dist/` for everything in it, not just the fingerprint.
    In scope by the user's call. (codex, user)
23. **`<TOOLS_FINGERPRINT>` conformance placeholder** is substituted wherever `<VERSION>` is (args, env, git
    `write` content) with the committed plugin fingerprint, documented in `conformance/README.md`, with runner
    tests per place. No golden normalization: no command prints the fingerprint. (codex)
24. **Rejected (codex): one twin-independent mismatch text.** Codex flagged that twin-dependent output breaks
    "output must not depend on the invoking twin". Rejected: pinning a case to the invoking twin is a documented
    case kind (AGENTS.md) with precedent (`doctor-twin-identity-*`), and the modified requirement states that
    `{install}` is the invoking twin's own command.
25. **The doctor requirement is REMOVED and re-ADDED under a new name** rather than MODIFIED: its old scenarios
    (version read, version differs, skill pins a version) no longer hold, and `openspec validate --strict` refuses a
    MODIFIED block that drops scenarios. (default)

## Risks / Trade-offs

- [Between releases a dev install from a checkout reports the last release's fingerprint, so `la-doctor` does not
  flag an outdated dev install] → same as the version today; contributors only.
- [A plugin released before this change meets newer tools] → mismatch with the reinstall command at that plugin's
  version, which is the right fix.
- [Docs edits under `conformance/` (README, INVENTORY.md) force a reinstall] → accepted by the issue's coverage
  decision; such edits usually ship with case changes anyway.
- [Between the bump commit and the published packages, main's plugin names a version not yet on PyPI/npm] →
  same window as today.

## Migration Plan

The first release after this change runs `scripts/release-bump`, which stamps the fingerprint for the first time.
Until then the committed files hold the fingerprint stamped by this change's implementation (computed over its own
HEAD), so a dev checkout stays healthy.
