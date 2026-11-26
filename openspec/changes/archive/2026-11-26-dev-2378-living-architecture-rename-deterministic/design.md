## Context

See proposal.md for why. The branch starts at `e3e2abf7` (PR #72's tip, "Release 0.14.0"), which carries the DEV-2320
split: `python/dr` (import `deterministic_refactor`), `node/dr`, `shared/dr`, `conformance/dr`, `plugin/dr` beside the
la counterparts, la depending on dr as a library. The PR's base is `egor/dev-2371-living-architecture-release-0140-the`.
Nothing named dr was ever released (`main` is at v0.13.0, pre-split), so no migration is needed.

Footprint: about 1.4k files name `dr` (most are conformance cases invoking `dr-*`), about 150 `Dr*`/`DR_*`
identifiers, about 380 files name `deterministic-refactor`/`deterministic_refactor`, and 82 corpus requirements in
seven specs.

Applicable principles (`architecture/system.arc42.md`; no element arc42 files exist):
1. Twins identical, decided by the conformance corpus: every renamed name and text changes identically in both twins.
2. Parameters, defaults, user-facing texts and command surfaces only from the shared contracts: where a twin
   hard-codes a package-level name today (`version("deterministic-refactor")`, `DR_SCHEMA = 'deterministic-refactor'`),
   the rename replaces the literal with a read from `shared/trmv/` (cli.yaml `package`/`plugin`/`doctor`, config.yaml
   `files`) instead of writing a new literal. Command ids used as manifest keys and entry-point module names stay
   literals, as today.
3. Language-specific code only in `trmv.lang` and `trmv.refactor`: unchanged.
4. Tools never import or execute target-repo code: unaffected.
5. `trmv` never depends on `la`: unchanged, enforced by model-truth.

## Goals / Non-Goals

**Goals:**
- Every name in the proposal renamed in both twins, the contract, the corpus, the plugins, the harnesses, docs, CI,
  scripts and tests, with no other behaviour change.
- The retired names cannot return unnoticed (guard test).
- The 0.14.0 release cannot publish an la plugin whose trmv dependency does not resolve (plugin-tag check).

**Non-Goals:**
- Renaming the `LA_*` environment variables trmv reads (`LA_FORWARDED`, `LA_CACHE_DIR`, `LA_PYRIGHT_*`): not dr names,
  and `LA_CACHE_DIR` shipped in 0.13.0.
- Any migration or alias for `deterministic-refactor.yaml`, the `dr-*` commands or the `dr` plugin (never released).
- A stub at `docs/deterministic-refactoring.md`.
- Updating PR #72's title and description (release sequence, after this merges); registry setup (trusted publishers,
  the npm placeholder).
- Renaming the `refactor` spec, the `refactor` config key or the `refactor` model element id.

## Decisions

Tags: `(user)` the user's choice, `(default)` an obvious default, `(codex)` a Codex finding folded in.

1. **Names**: package `type-rename-move` on PyPI and npm (npm refuses `trmv`); Python import, commands (`trmv-*`),
   plugin (`trmv`, tag `trmv--v<version>`), skill namespace (`trmv:`) and config file (`trmv.yaml`, series `[0.14.0]`)
   `trmv`; schema `trmv.schema.json`; manifest `package: type-rename-move`, `plugin: trmv`, `doctor: trmv-doctor`;
   finding ids `format.trmv-*`; every "dr" in a text becomes "trmv"; install hints and twin runners name
   `type-rename-move`; layout, identifiers (`TRMV_*`, `Trmv*`, `trmv*`, `trmv_*`), test and case names follow.
   `la-typecheck` stays the deprecated alias, now of `trmv-typecheck` ("la-typecheck is deprecated and will be removed
   in 0.15.0; run trmv-typecheck instead"). No `dr-*` aliases. (user, via the issue and its comment)
2. **Skill** `dr:deterministic-refactor` → `trmv:rename-move` (directory `plugin/trmv/skills/rename-move`), rather than
   `trmv:refactor` (repeats the overpromise, blurs the procedure with the mutator) or `trmv:trmv` (says nothing). The
   other skills keep their names under `trmv:`. (user)
3. **Concept** "deterministic refactoring" → "verified renames and moves"; `docs/deterministic-refactoring.md` →
   `docs/rename-and-move.md` titled "Renames and moves"; README heading "Just renames and moves"; model element title
   `'Rename and move'`; skill heading and package docstring follow. No stub at the old path: the only dead link is the
   0.13.0 registry README, which 0.14.0 supersedes. Rejected: a stub (a permanent exception for a short-lived link),
   keeping the term (keeps the overpromise, two names for one tool). (user)
4. **Harness edits** (user, approved wording):
   - `architecture/index.yaml`: `python: {source_roots: [python/trmv/src, python/la/src], root_packages: [trmv,
     living_architecture]}`; `typescript: {source_root: node, root_packages: [trmv/src, la/src]}`; every
     `python.dr.<x>` in `cross_cutting_specs` `touches:` → `python.trmv.<x>`.
   - `architecture/model.c4`, in both roots: `dr = node 'deterministic-refactor'` → `trmv = node 'type-rename-move'`;
     `package 'deterministic_refactor'` → `package 'trmv'` (typescript `'dr/src'` → `'trmv/src'`);
     `refactor = node 'Deterministic refactoring'` → `refactor = node 'Rename and move'`; every `dr.<x> -> dr.<y>` →
     `trmv.<x> -> trmv.<y>`; `la -> dr` → `la -> trmv`. Nested ids and spec mappings unchanged; `views.c4` unchanged;
     diagrams regenerated with `la-arch-diagrams`.
   - `architecture/system.arc42.md`, Purpose and context, first sentences: "Two packages, each with a Claude Code
     plugin: `type-rename-move` (`trmv-*` commands, plugin `trmv`): verified renames and moves and the type-check gate;
     and `living-architecture` (`la-*` commands, plugin `la`): the architecture cross-check, the conventions gate, the
     review helpers and the PR flow. la depends on trmv." (rest of the paragraph unchanged)
   - Principle 1 tag: `[enforced: test:python/dr/tests/test_conformance.py]` →
     `[enforced: test:python/trmv/tests/test_conformance.py]`.
   - Principle 3: "Language-specific code lives only in `trmv.lang` and `trmv.refactor`. [review]"
   - Principle 5: "`trmv` never depends on `la`. [enforced: arch_check:model-truth]"
   - Rationale, second paragraph: "Verified renames and moves are useful without the architecture workflow, so they
     are their own package that la uses as a library; the dependency runs one way so trmv installs and runs alone."
5. **DEV-2371 comment** (the global CLAUDE.md instructions) edited in place to this text, as the last pr-implement
   task (user, approved wording):

   > ## Global CLAUDE.md: the trmv renames (from DEV-2320 and DEV-2378)
   >
   > After the release, replace the large-scale-refactor rule at the end of `~/.claude/CLAUDE.md` with this approved edit:
   >
   > ```diff
   >  - For ANY large-scale refactor (renames/moves of classes, functions, attributes, modules across many files), ALWAYS
   > -load the `la:deterministic-refactor` skill and follow its procedure step by step with its own commands
   > -(`la-typecheck`, `dr-refactor` dry-run → review → `--apply`, the full gate). Never hand-roll or chain `--apply` runs.
   > +load the `trmv:rename-move` skill and follow its procedure step by step with its own commands
   > +(`trmv-typecheck`, `trmv-refactor` dry-run → review → `--apply`, the full gate). Never hand-roll or chain `--apply` runs.
   > ```
   >
   > Order matters: apply it only after the maintainer re-setup from the DEV-2378 PR's description (link `~/.claude/skills/trmv` to `plugin/trmv`, re-link `~/.claude/skills/la` to `plugin/la`, and reinstall the editable tools with `uv tool install -e python/la --with-editable python/trmv --with-executables-from type-rename-move`). Until then the `trmv:` skill name does not resolve.
   >
   > `la-typecheck` keeps working as a deprecated alias of `trmv-typecheck` until 0.15.0, so the old line degrades rather than breaks. `la:deterministic-refactor` has no stub, though, so the skill name breaks as soon as the plugin links move.
   >
   > The other CLAUDE.md references (`la:reply-to-pr-thread`, `la:fetch-failed-pr-checks`, the `la:pr` stage names) are unchanged by DEV-2320 and DEV-2378. The fetch-command rename from DEV-2363 ships in 0.15.0 (DEV-2374).
6. **Guard test**, permanent, in la's suite, rather than a one-off grep: work branched before the rename (anything on
   the 0.13.0 `main`) would reintroduce the names through a merge. (user) Its scope (codex finding 5, user): tracked
   text file contents, case-sensitive, for `\bdr\b`, `\bdr[_./-]`, `\bDR_`, `\b[dD]r[A-Z]` and
   `deterministic[-_ ]refactor`, and tracked paths for a `dr` path component; each hit reported as file:line. Excluded:
   the lockfiles (base64 integrity hashes can hold `+dr/`), the guard test's own file (it spells the patterns; the
   alias `la-typecheck` names no retired name, so it needs no exclusion), all of `openspec/changes/`
   (archived changes are history; an active change's RENAMED `FROM:` lines hold the old names), and each
   `openspec/specs/<cap>/spec.md` while a non-archived `openspec/changes/*/specs/<cap>/` exists (the corpus is pending
   that change's archive). (user)
7. **Spec deltas**: full MODIFIED deltas for every corpus requirement naming the tools (82) and RENAMED for the 7 whose
   titles carry a name, generated by `rename_deltas.py` (in this change folder) from the corpus, rather than
   `skip_specs` plus a hand rewrite: command and package names are observable behaviour, and the archive should carry
   them. A delta cannot rename a scenario title or a Purpose, so the 26 scenario titles and the Purposes of `refactor`,
   `typecheck` and `doctor` keep their names in the deltas and are renamed directly in the corpus at archive time with
   the same substitution. (default; the scenario-title handling found while emitting the change)
8. **Goldens are edited by substitution in pr-tests, never regenerated**; in pr-implement `LA_UPDATE_GOLDENS=1` must
   produce no diff, and a diff is a bug. (default)
9. **Commit order**: each rename-only commit (`git mv`) is paired with the edit commit right after it, and the pair ends
   green; moves stay separate from edits so git records them as renames. (codex finding 1)
10. **Moves**: directories by `git mv`; the Python package `deterministic_refactor` → `trmv` by `dr-refactor`
    (dogfooding); where the tool cannot do a step (its own top-level package, npm bare specifiers), a `git mv` plus a
    textual rewrite, without stopping. Each is verified with the checkers directly (`commands.typecheck`: basedpyright
    over `python`, `tsc -p node`) and the tests, since `trmv-typecheck` does not exist yet at that step. (default,
    following the user's "don't be too picky about the tools"; verification per codex finding 2)
11. **Names from the contract** where a twin hard-codes a package-level name today (principle 2). (default)
12. **Release rule across layouts**: `FORMATS_FILE` becomes `shared/trmv/config.yaml`; the `shared/config.yaml`
    fallback for pre-split releases stays; the release-rule tests cover the real `v0.13.0` → 0.14.0 transition
    (`trmv.yaml: [0.14.0]`, `living-architecture.yaml` appending `0.14.0`). (codex finding 3)
13. **Duration files**: the test and case ids in `python/{trmv,la}/tests/durations/{suite,cross-python,cross-typescript}.json`
    are renamed with the tests; `test_ci_split` stays green. (codex finding 4)
14. **Plugin-tag check**: `scripts/release-check` refuses unless `trmv--v<version>` exists and points at the release
    tag's commit (spec: "release-check verifies the trmv plugin tag"); the runbook in `docs/development.md` tags
    `trmv--v<version>` from `plugin/trmv`. Searched Linear ("plugin tag", "release-check"): no existing issue. (user,
    codex finding 6)
15. **Lockfiles regenerated**, never substituted: `uv lock` in `python/` and `npm install --package-lock-only` in
    `node/` after the manifest changes, then `uv sync --locked --all-packages` and `npm ci`. (codex finding 7)
16. **npm wiring**: `node/la/tsconfig.json` `paths` map `type-rename-move` and `type-rename-move/*` to `../trmv/src`;
    the pack test asserts la's tarball imports only `type-rename-move/<module>` and that every export subpath resolves
    from the packed tarballs. (codex finding 8)
17. **Package metadata**: descriptions unchanged (already the issue's text); keywords are today's plus rename, move,
    refactor, refactoring, typecheck, python, typescript, verified, imports, on both packages. Versions stay 0.14.0.
    (default)
18. **`LA_*` environment variables out of scope.** (default)

## Risks / Trade-offs

- [A blind substitution hits an unrelated `dr` (English, hashes, base64)] → the substitution is boundary- and
  case-aware; lockfiles are regenerated, not substituted; every golden diff is a substitution, checked by the
  no-diff `LA_UPDATE_GOLDENS=1` run.
- [`dr-refactor` cannot rename its own top-level package, or breaks its editable install mid-run] → fall back to
  `git mv` plus a rewrite, verified by the checkers and tests (decision 10).
- [One very large PR] → moves committed as renames separately from edits; reviewers go commit by commit.
- [The maintainer's local setup breaks: `~/.claude/skills/la` points at the pre-split `plugin/`, the editable tools
  install `deterministic-refactor`] → the PR description gives the re-link and reinstall commands.
- [A plugin tag cut at another commit makes `release-check` refuse] → intended: the la plugin's dependency must
  resolve to the released trmv plugin.

## Migration Plan

None for users: nothing named dr was released. The release follows the issue's sequence: merge into
`egor/dev-2371-living-architecture-release-0140-the`, update PR #72, merge it into `main`, tag `trmv--v0.14.0` from
`plugin/trmv`, then `v0.14.0`; `publish.yml` publishes `type-rename-move` before `living-architecture`.
