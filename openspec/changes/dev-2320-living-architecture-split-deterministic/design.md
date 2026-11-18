## Context

See proposal.md for why. Today one package per ecosystem (`living_architecture` in `python/src`, `node/src`) holds
every module, one `shared/` contract, one plugin in `plugin/` and one conformance corpus. Measured import graph of the
modules that move to dr (Python; npm is the same): `refactor` imports `changes`, `config`, `contract`, `lang`, `twin`,
`typecheck` and the package root's `__version__`/`NATIVE_LANGUAGE`; `typecheck` imports `config`, `contract`, `lang`,
`twin`; `lang`, `twin`, `changes`, `config` import only `contract` (and the root). Nothing imports `refactor`
except `cli`. On the la side, `archcheck` imports `c4`, `config`, `contract`, `lang`, `twin`; `conventions` and
`affected` import `changes`, `config`, `contract`, `lang`, `twin`; `doctor` imports `config`, `contract`.

`repo_languages` (`config/languages.py`) filters files through `conventions.exempt`, so language detection depends
on an la key today. `architecture/index.yaml` allows one `source_root` per language; PR #28 added `root_packages`
under that one import root only. `uv_build` refuses a module root outside its project ("Module root must be inside
the project"), so the two Python packages cannot share one `src/`.

Applicable principles (`architecture/system.arc42.md`; no element arc42 files exist): 1 twins identical, decided by
the conformance corpus; 2 parameters, defaults, texts and command surfaces only from the shared contracts;
3 language-specific code only in `dr.lang` and `dr.refactor`; 4 tools never import or execute target-repo code
except a configured command; 5 (new) `dr` never depends on `la`.

## Goals / Non-Goals

**Goals:**
- dr installs and runs alone, in Python and TS/JS repos, with its own plugin and config file.
- la reuses dr as a library within a language; cross-language routing stays inside each package's twin forwarding.
- Every observable behaviour of today's commands is preserved apart from the deliberate changes in the specs, each
  golden diff explained.

**Non-Goals:**
- dr in its own repository.
- `dr-migrate` (arrives with the first dr format bump).
- Stub skills for the moved skills.
- Moving `la-check-conventions`, `la-count-comments` or `la-affected-tests` to dr.
- `source_roots` for TypeScript (its units are paths; one `source_root` with several `root_packages` suffices).

## Decisions

Tags: `(user)` the user's choice, `(default)` an obvious default, `(codex)` a Codex finding folded in.

1. **Issue decisions 1–8** carry over: two packages and plugins in this repo nested by language, `shared/dr` and
   `shared/la` with a hash each, lockstep versions with la pinning dr's minor, one config file per target repo, la
   calls dr as a library, a conformance tree and inventory per package with one runner, `dr-` names and the `dr:`
   namespace with `la-` aliases for one minor, and a `dr` node with only `la -> dr`. (user, via the issue)
2. **Plugin dependency**: la's `plugin.json` declares `dependencies: [{name: dr, version: "~0.13.0"}]`, so installing
   la installs dr. Verified: `claude plugin validate` 2.1.322 accepts this form and rejects a non-array. This answers
   the issue's open question. (default)
3. **Python `source_roots`** in `index.yaml` (a list replacing `source_root`; each root package under exactly one
   entry; unit ids stay dotted), rather than per-root `{package, source_root}` entries (same meaning, more verbose, a
   third root form). TypeScript keeps one `source_root` and rejects `source_roots`. (user)
4. **Names**: PyPI and npm `deterministic-refactor` (import `deterministic_refactor`), config
   `deterministic-refactor.yaml`, plugin `dr`, marketplace unchanged; no dr local file, since the local file only
   overrides la keys. Rejected `living-architecture-dr` (ties dr to la) and `dr.yaml` (too generic). (user)
5. **Conventions, count-comments and affected-tests stay in la** under their `la-` names: they serve la's workflow;
   narrowing tests after a refactor would weaken the dr gate, which runs the full suite. (user)
6. **Top-level `exempt`** defined by dr's schema and embedded in la's, read by language detection and the conventions
   gate; `living-architecture.yaml` moves to format 0.13.0 and `la-arch-migrate` moves the key. Rejected keeping
   `conventions.exempt` in dr's schema (a dr-only config would say `conventions:` forever). In an la repo the key
   stays in the one `living-architecture.yaml`. (user)
7. **Per-file format series** in `shared/dr/config.yaml` (`living-architecture.yaml: [0.4.0, 0.13.0]`,
   `deterministic-refactor.yaml: [0.13.0]`); each command checks the file it read. Rejected one shared series (an
   la-only bump would disturb dr-only repos and need a restamp-only `dr-migrate`) and skipping the check on the la
   file (a stale dr could misread a newer config). An la-only format bump changes dr's hash, harmless in lockstep.
   (user)
8. **`la-typecheck` alias** prints one stderr deprecation line naming `dr-typecheck` and 0.14.0; stdout and exit
   unchanged; not printed under `LA_FORWARDED`. Rejected a silent alias (nobody would migrate before removal). (user)
9. **dr owns more than the issue lists**: `config` (loading, YAML profile, schema, defaults, format check, language
   detection), `twin` and `changes`, because `refactor` and `typecheck` import them; plus `dr-doctor`, `dr-config` and
   a `dr:init` skill taking la:init's type-check baseline step. (user, approved extension)
10. **No stub skills**; la's skills name the `dr:` skills; the user's global `CLAUDE.md` edit (`la:deterministic-refactor`
    → `dr:deterministic-refactor`, `la-typecheck` → `dr-typecheck`) is proposed at the end. (user)
11. **One change, one PR**, ordered so each step lands green in its own commit, rather than precursor PRs for
    `source_roots` and `exempt` (two more full cycles; 0.13.0 could not ship until all landed). (user)
12. **Harness edits** (approved wording):
    - `architecture/index.yaml`: `python: {source_roots: [python/dr/src, python/la/src], root_packages:
      [deterministic_refactor, living_architecture]}`, `typescript: {source_root: node, root_packages: [dr/src,
      la/src]}`; spec ids and `touches:` move to nested ids (`python.refactor` → `python.dr.refactor`).
    - `architecture/model.c4`: `python = system 'PyPI twins'` with `dr = node 'deterministic-refactor'` (package
      `deterministic_refactor`; nested contract, config, lang, twin, changes, typecheck (specs typecheck), refactor
      (specs refactor), doctor, cli) and `la = node 'living-architecture'` (package `living_architecture`; nested
      contract, config, cli, c4, archcheck, conventions, review, doctor, affected, specs as today), nested arrows as
      measured, `la -> dr` the only cross arrow; `typescript = system 'npm twins'` the same with packages `dr/src` and
      `la/src`. `twin-forwarding` moves with `twin` to `python.dr.twin`. `views.c4`: the `system` and `npm` views at
      view depth 2.
    - `system.arc42.md` Purpose and context, replacing the paragraph: "Two packages, each with a Claude Code plugin:
      `deterministic-refactor` (`dr-*` commands, plugin `dr`): verified renames and moves and the type-check gate; and
      `living-architecture` (`la-*` commands, plugin `la`): the architecture cross-check, the conventions gate, the
      review helpers and the PR flow. la depends on dr. Each package has two native implementations (twins) that obey
      its contract in `shared/<package>/`: the PyPI packages in `python/` serve Python repos, and the npm packages in
      `node/` serve TS/JS repos. The skills in `plugin/<package>/` drive the commands." (user, approved wording)
    - Principle 1 tags: "[enforced: test:python/dr/tests/test_conformance.py]
      [enforced: test:python/la/tests/test_conformance.py] [enforced: test:node/scripts/conformance.mjs]".
      (user, approved wording)
    - Principle 2: "Parameters, defaults, user-facing texts and command surfaces come only from the shared
      contracts. [review]" (user, approved wording)
    - Principle 3: "Language-specific code lives only in `dr.lang` and `dr.refactor`. [review]"
      (user, approved wording)
    - New principle 5: "`dr` never depends on `la`. [enforced: arch_check:model-truth]" (user, approved wording)
    - Rationale, appended: "Verified refactoring is useful without the architecture workflow, so it is its own
      package that la uses as a library; the dependency runs one way so dr installs and runs alone."
      (user, approved wording)
13. **New cross-cutting spec `doctor`** (`touches: [python.dr.doctor, python.la.doctor]`) holding only the new
    doctor behaviour, rather than two specs that would cross-reference each other. (user)
14. **Layout**: a uv workspace at `python/` (members `dr`, `la`, and a dev-only unpublished `conformance` runner),
    one `uv.lock`; a private npm workspace root at `node/` (`dr`, `la`), one lockfile; one shared
    `conformance/fixtures/`; la's message lookup tries la's registry, then dr's, with ids unique across both. (default)
15. **Identities and hints**: `dr-doctor --twin` → `<lang> <version> <dr-hash>`, `la-doctor --twin` →
    `<lang> <version> <la-hash> <dr-hash>`; `--contract-hash` prints the package's own hash; `la-doctor` checks the
    `dr-doctor` on `PATH`; la's install hints add the dr commands (`--with-executables-from deterministic-refactor`,
    or `deterministic-refactor@V` beside la on npm) because `uv tool install` exposes only the main package's
    executables. `uvx --from living-architecture` can run a dependency's executable but warns, so each package keeps
    its own runner. (default)
16. **Migration algorithm**: a textual move of the `conventions.exempt` entry's lines to after `format`, dedented,
    the emptied `conventions` removed; flow-style `conventions`, anchors, aliases, tags or a merge key in it are not
    migratable. Re-serializing the YAML would lose comments. (default)
17. **`la:init` hands the dr keys and the baseline step to `dr:init`**, so the language docs live only in the dr
    plugin (`plugin/dr/languages/`); an extension of decision 9's "baseline step". (default, flagged extension)
18. **Schema composition** (codex finding 1): la's schema stays closed (`additionalProperties: false`) and takes each
    dr key by a property-level `$ref` to dr's schema (registered from dr's snapshot under its `$id`), the pattern
    `living-architecture.local.schema.json` already uses. Both default fillers learn to follow `$ref` exactly as
    inline definitions. `allOf` of two closed schemas would reject each other's keys. (codex)
19. **TypeScript configs** (codex finding 2): `node/la/tsconfig.json` (no emit; typecheck, lint and arch-check) maps
    `deterministic-refactor` to `../dr/src`, so la typechecks without a dr build and arch-check measures the la→dr
    edge (a `.d.ts` target is invisible). `node/la/tsconfig.build.json` drops the mapping and resolves dr's built
    declarations through the workspace link; dr builds first. A pack test proves la's tarball imports only
    `deterministic-refactor`, never `../dr/src`. (codex)
20. **Package-aware runner** (codex finding 3): a case's tree (`conformance/dr` or `conformance/la`) decides its
    package: manifest, format series, version, contract-hash placeholder, Python entry-point directory and npm bin
    directory. Both packages' commands are on `PATH` (la needs dr's), host runners are hidden as today. A self-test
    refuses a dr case invoking an `la-*` command and vice versa. la's facts documents (arch-check, conventions,
    affected) carry la's hash; the identity handshake already pins dr's. (codex)
21. **Version bump with the format** (codex finding 4): the lockstep bump to 0.13.0 lands in the same commit that
    appends format 0.13.0 (step 2), because a test requires the current format to be no newer than every version;
    later steps update the new manifests and lockfiles atomically. (codex)
22. **la's dr surface** (codex finding 5): la imports from dr only through these public modules —
    `deterministic_refactor.contract` (snapshot loader, `message`, schema, YAML profile, glob, repr, OS errors),
    `.config` (`find_repo_root`, `load_config`, `repo_languages`, `source_files`, `language_fact`, format check and
    stamping, file names), `.lang` (units, edges, source), `.twin` (forwarding parametrised by package identity) and
    `.changes`; the npm side mirrors these as `deterministic-refactor/<module>` exports. la keeps no copy of any of
    them. The extra "no copies" test is rejected: model-truth with no `dr -> la` arrow already enforces the direction,
    and copying cannot be tested meaningfully. (codex; test rejected (codex))
23. **Per-package release check** (codex finding 6): `python/dr == node/dr == hash(shared/dr)` and
    `python/la == node/la == hash(shared/la)`; the two hashes may differ; a drift case per snapshot. (codex)
24. **Exact workspace commands** (codex finding 7): `uv build --package deterministic-refactor` /
    `--package living-architecture` (artifacts under `python/dist/`), per-member pytest/ruff/basedpyright, `npm -w dr`
    / `npm -w la` build, pack and publish, dr published before la on both registries; isolated installs of all four
    artifacts, an la-only install resolving dr, and a `uv tool install` proving which executables reach `PATH`.
    (codex)
25. **One format check per invocation** (codex finding 8): every public entry point checks its package's file once
    in the invoking twin, before forwarding; dr library calls made from la receive the resolved config. (codex)
26. **"Tracked" wording** (codex finding 9): language detection keeps counting tracked files and untracked files
    that are not ignored (`git ls-files --cached --others --exclude-standard`); only the exempt key changes. (codex)
27. **Required new conformance cases** (codex finding 10): listed in tasks.md. (codex)
28. **Interim `doctor` mapping**: until the model split (task 8.1), `cross_cutting_specs.doctor` touches
    `[python.doctor]` so `la-arch-check` stays green; 8.1 rewrites it to the approved form. (user, approved wording)

## Risks / Trade-offs

- [Moves across source roots and packages may exceed `dr-refactor`'s reach] → try it first (dogfooding, as the issue
  asks); if it cannot move a module across source roots or packages, stop and ask before falling back to `git mv`
  plus a verified import rewrite.
- [One very large PR; CodeRabbit may truncate] → ordered, individually green commits; moves recorded as renames;
  reviewers go commit by commit.
- [Golden churn hides a real regression] → every golden diff carries a reason (path rename, hint text, ok line,
  package name); unexplained diffs block.
- [Users install la without the dr executables] → la's install hints include them; `la-doctor` reports a missing or
  mismatched `dr-doctor`.
- [Target repos must migrate to format 0.13.0] → `la-doctor` already names `la-arch-migrate`; the step is automatic
  and refuses shapes it cannot move faithfully.
- [The maintainer's local setup breaks: `~/.claude/skills/la` points at `plugin/`, the editable uv tool is one
  package] → the PR description gives the re-link and reinstall commands.

## Migration Plan

Release 0.13.0 of both packages and plugins together (dr first on each registry). Target repos run `la-arch-migrate`
once; scripts calling `la-typecheck` switch to `dr-typecheck` before 0.14.0, which removes the alias. Rollback is
installing 0.11.x, which reads format 0.4.0 only, so a migrated repo would need its `exempt` moved back by hand.
