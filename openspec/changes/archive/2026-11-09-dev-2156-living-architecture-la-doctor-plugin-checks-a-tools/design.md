## Context

Users install the plugin from the marketplace (`.claude-plugin/marketplace.json`, source `./plugin`, no ref), so
installs and updates take `plugin/` from main's HEAD, whose `plugin.json` names the last release until the next
bump. Both twins already have `is_version`/`compare_versions` (config's `format` module) for the repo format; the
doctor imports config. `Publish` runs on a published GitHub release, so the tag exists before `release-check` runs;
both workflows check out with depth 1 and no tags today.

Architecture: touched elements are `python.doctor` / `typescript.doctor` and `contract`; the release rule lives
in `scripts/`, outside the model. System principles 1 (twins identical, conformance decides) and 2 (texts and
flags only from `shared/`) apply; 3 and 4 do not. No arc42 or model edit. The spec attaches to the cross-cutting
`shared-contract` capability.

## Goals / Non-Goals

**Goals:** a release that leaves the tools unchanged needs no reinstall; any tool change still forces one; a
release breaking the rule is caught on its bump PR, before a tag exists.

**Non-Goals:**
- The twin handshake (`la-doctor --twin`, facts `version`/`contract_hash`) keeps exact versions.
- No `release-bump` script and no tools fingerprint.
- The `format` bump in `shared/config.yaml` stays a manual release step.
- Release branches/backports get no special handling (the repo has none).

## Decisions

1. **Minor-version scheme instead of a tools fingerprint.** Options: stamp a fingerprint of the tool sources into
   the plugin and both twins and compare it; or compare major.minor under an enforced release rule. Taken: the
   minor scheme, the same guarantee with far less machinery (no stamped files, no packaging of a fingerprint). (user)
2. **`--expect` is removed**: no caller, and it encoded exact version equality. (user)
3. **`prepack` runs `npm run build`** before copying README/LICENSE: a direct `npm pack` shipped a stale or missing
   `dist/`. (user)
4. **Version form `<digits>.<digits>.<rest>`**, rest non-empty and free, so `0.4.1-rc1` is valid; options were
   strict X.Y.Z or a free rest. (user)
5. **A non-conforming version is `doctor.plugin-invalid`**, not a mismatch, whose advice would name an
   uninstallable version. (user)
6. `doctor.plugin-invalid: '{path} is not valid JSON with a "version" of the form <major>.<minor>.<rest>'`
   (user, approved wording)
7. `doctor.version-mismatch: 'installed la tools are {installed}, but plugin {expected} needs {series}.x; reinstall
   them with: {install}'` (user, approved wording)
8. **The rule is enforced in `release-check` and on the bump PR**, both through one function under `scripts/`;
   options were publish time only, or also PR time. PR time catches a wrong bump before a tag exists. (user)
9. **Tool inputs include the build inputs** (`node/scripts/`, `node/tsconfig*.json`) and the manifests and
   lockfiles (`python/pyproject.toml`, `python/uv.lock`, `node/package.json`, `node/package-lock.json`), the latter
   compared as parsed data after setting the package's own version fields to V in the previous release's copy.
   Options: the issue's four source roots only (a dependency bump could ship as a patch) or these too; a textual
   replace of the version string was rejected, as a dependency moving from the previous version to V cancels out.
   (codex, user)
10. **ASCII digits only; major/minor compared without numeric conversion** (strip leading zeros, then compare
    digit strings by length then value, as `compare_versions` does), so a component beyond 2^53 compares the same in
    JS; lone surrogates stay invalid because the version is printed in the install command and Python cannot print
    one. (default; the no-conversion part codex)
11. **The mismatch names the invoking twin's install command** at the plugin's version; its byte-exact cases are
    pinned per twin, for a plain and a prerelease-style version. (default; the prerelease cases codex)
12. **Previous release** = highest reachable `vX.Y.Z` tag below V; other tag forms ignored. (default)
13. **`release-check` fails on a shallow repo, with no reachable previous release, or when HEAD is not the tag's
    commit** (lightweight or annotated), since the rule diffs against HEAD. No first-release exception: the repo is
    past it. (codex)
14. **The PR-time test applies the rule only while no tag for the current version exists**: between releases main
    legitimately holds unreleased tool changes under the last release's version, and forcing a bump per PR would
    make main's `plugin.json` name an unpublished version. It skips without release tags, fails on GitHub Actions.
    `ci.yml` and `publish.yml` check out with `fetch-depth: 0`. (default)
15. **`<MAJOR>`/`<MINOR>` conformance placeholders** (the installed version's), substituted in inputs wherever
    `<VERSION>` is (args, env, fake executables, `write:` steps); a golden that would show the installed series
    uses a `normalize` pattern instead, so goldens survive a major or minor bump. (default; the golden rule codex)
16. **Release-rule tests run whole histories through `release-check`**: tool change then minor bump, unchanged
    patch, tool change then patch, plugin/docs-only patch. (codex)
17. **The doctor requirement is REMOVED and re-ADDED** under a new name: its old scenarios no longer hold and
    `openspec validate --strict` refuses a MODIFIED block that drops scenarios. (default)
18. Rejected (codex): **choose the previous release by ancestry, for backport branches.** Only reachable tags below
    V count, so a backport branch sees its own predecessor; the repo has no release branches.
19. Rejected (codex): **apply the rule on every PR.** It would force a version bump per tool-changing PR, making
    main's `plugin.json` name an unpublished version (see 14).
20. Rejected (codex): **restrict the rest to versions both package managers accept.** The user chose a free rest,
    and a shipped `plugin.json` always names a published version.

## Risks / Trade-offs

- [A tools hotfix cannot ship as a patch] → versions climb faster; cosmetic before 1.0.
- [A plugin released before this change meets newer tools, or newer plugin meets older tools] → the older side's
  doctor compares exact versions and reports a mismatch with that side's advice; reinstalling fixes it.
- [Between the bump commit and the published packages, main's plugin names a version not yet on PyPI/npm] → same
  window as today.
