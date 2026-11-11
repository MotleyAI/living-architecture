## Context

See proposal.md for motivation. Constraints that shape the approach:

- The twin rule (AGENTS.md): both twins produce byte-identical output; `shared/` is the only source of command
  surfaces and texts; the conformance corpus decides.
- `architecture/system.arc42.md` principles that apply:
  1. Twins identical — conformance cases for every observable branch, run through both twins.
  2. Parameters, texts and command surfaces only from the shared contract — `cli.yaml`, `findings.yaml`, a schema.
  3. Language-specific code lives only in `lang` and `refactor` — every Python/TypeScript import scan and file
     resolution sits in each twin's `lang`; `changes` and `affected` are language-neutral.
  4. Tools never import or execute target-repo code — the command parses files, never imports them.
- Model-truth: every new package is a node of `architecture/model.c4` and every measured import an arrow.
- Today `resolve_base_ref` and `changed_source_files` (and their TS counterparts) live in the conventions gate,
  and `is_test_file`/`isTestFile` too; the TS import resolver (`node/src/lang/imports.ts`) walks only visible,
  non-test files under the architecture roots, and the Python one (`lang/units.py`) only dotted modules under
  `source_root` + `root_packages`, both runtime-only.

## Goals / Non-Goals

**Goals:**
- An exact, deterministic, offline (apart from the best-effort fetch) selector whose only error is over-selection.
- One "what did this branch change" implementation shared by `la-check-conventions` and `la-affected-tests`.

**Non-Goals:**
- Parsing CI logs for failing test ids (the agent has them from `la-fetch-failed-pr-checks`).
- Running tests; the command only prints paths (the skill runs them with the repo's runner).
- Golden, conformance, data-file, config and fixture/conftest fan-out (agent's judgement, per the skill wording).
- Coverage-based selection (needs a prior full run and local state).
- Filtering printed files the runner does not collect (helpers, fixtures): not decidable without runner config.
- Any release or version bump.

## Decisions

### Structure
- **`changes` node** (`living_architecture.changes`, `src/changes`): base-ref resolution (`origin/<branch>`,
  best-effort fetch, `rev-parse --verify`) and the git change listing — NUL-delimited (`-z`), `--no-renames`, with
  or without deletions and untracked files. The conventions gate calls it with its current filter (ACMR, no
  untracked), so its behaviour and goldens are unchanged. The git texts move from `conventions.*` to `changes.*`
  in `findings.yaml` with identical wording.
- **`is_test_file`/`isTestFile` → `contract`**, beside `language_of`: a pure function of `languages.yaml`.
- **`affected` node** (`living_architecture.affected`, `src/affected`): the changed set, per-language routing,
  the reverse walk, test-glob matching, the internal request/response, rendering.
- **`lang` API** (each twin, own language only): given the repository root, the graph files and the deleted paths,
  return the dependency edges as repo-relative path pairs. Nothing language-specific leaks into `affected`.
- **`model.c4`** (user, approved wording), in both roots:
  ```
  changes = node 'Change set' { metadata { package 'living_architecture.changes' } }   // 'src/changes' in typescript
  affected = node 'Affected tests' { metadata { package 'living_architecture.affected'  specs ['affected-tests'] } }
                                                                    // 'src/affected', no specs, in typescript
  cli -> affected
  affected -> changes
  affected -> lang
  affected -> config
  affected -> contract
  affected -> twin
  conventions -> changes
  changes -> config
  changes -> contract
  ```
  (written in the model's multi-line metadata style). If the measured imports differ, the correction is brought
  back to the user for approval, never applied silently.

### Selection
- **Changed set** = `git diff -z --name-only --no-renames <base>...HEAD` ∪ `git diff -z --name-only --no-renames
  HEAD` ∪ `git ls-files -z --others --exclude-standard`, deletions included. Graph files =
  `git ls-files -z --cached --others --exclude-standard` filtered to the language's source extensions, plus the
  language's deleted changed paths. Node identity = the lexical git path (repo-relative POSIX).
- **Path policy**: a path that is not valid UTF-8 or contains CR/LF exits 2 naming it (it cannot be printed one per
  line, and the twins cannot agree on lossy decodings).
- **Python edges** = union of an `ast` scan (every `Import`/`ImportFrom`, `TYPE_CHECKING` bodies included) and a
  lexical scan (backslash continuations joined; `import a.b as c, d` and `from <dots><mod> import <names |
  (parenthesized, multi-line) | *>` anywhere in the text). Resolution per the spec: dotted-suffix match over all
  graph files with parent `__init__.py`s, `from a.b import c` also probing `a.b.c`, relative imports by directory
  level probing modules, names and the package `__init__.py`, and each file's own package chain.
- **TypeScript edges**: a new all-specifiers scan beside `runtimeSpecifiers` (which `la-arch-check` keeps using
  unchanged): static/dynamic imports and exports, `import x = require()`, literal `require()`, type-only forms,
  `ImportTypeNode`, `/// <reference path>`. Resolution per file under the nearest `tsconfig.json` (projects
  loaded once per config and cached; `owner()` within that config's projects, else its root project). A virtual
  host layer makes deleted paths exist: `fileExists` true, their ancestors `directoryExists`, `realpath` the
  identity; resolution caches are built on that host. Edge target = the resolved path's repo-relative form, or for
  a path through `node_modules` its real path when that is inside the repo and outside `node_modules`. Unresolved
  relative specifiers: the extension-candidate fallback in the spec.
- **Walk**: reverse adjacency, BFS from every changed or deleted file of the language, visited set; output =
  changed-existing ∪ reached, filtered by `test_globs`, deleted paths excluded.

### Twins
- `shared/cli.yaml`: `la-affected-tests` neutral (no `native`), options `--base` (string) and internal
  `--language {python,typescript}`, `require_one_of: [base, language]`.
- Internal mode: `la-affected-tests --language L` reads a JSON document on stdin (changed paths with a deleted
  flag), computes L natively, and prints a JSON document `{language, version, contract_hash, tests: [...]}`, both
  validated by a new shared schema. The invoking twin checks identity and schema (as `request_conventions_facts`),
  unions, sorts by code point and renders once. Stdout is written only after everything succeeded, so exit 2
  never leaves partial output.

### Decisions log
1. **Python import resolution: file-based suffix matching, no config.** Options: require the
   `architecture/index.yaml` language section (dead in `architecture: false` repos, tests outside roots still
   unresolved); a new config key for import roots (a knob to maintain, empty by default); file-based. Taken:
   file-based — works in every repo, covers namespace packages and rootdir-inserted imports, never under-selects a
   repo file; collisions only over-select. (user)
2. **Walk from every changed or deleted file, test or not** (extends the issue's "non-test source module"). Options:
   non-test only (a changed test helper selects none of its importers); every file. Taken: every file — closes an
   exactly computable gap with one uniform rule; conftest stays out since nothing imports it. (user)
3. **Type-only edges count.** Options: runtime only (misses tests under type-checking runners such as ts-jest,
   `vitest --typecheck`, pytest-mypy); all imports. Taken: all imports — under-selection is the failure to avoid.
   (user)
4. **Shared helpers extracted in this change.** Options: `affected -> conventions` (a test selector depending on
   the conventions gate); extract `changes` + move `is_test_file` to `contract`, as a separate `la:arch-cleanup`
   PR first or in this change. Taken: extract here — the extraction exists for this feature, and one change-set
   implementation serves both commands. (user)
5. **`model.c4` edit** as quoted under Structure. (user, approved wording)
6. **Part B skill wording**, applied verbatim (user, approved wording):
   - `plugin/skills/pr/SKILL.md`, new section after "Commit at the end of every stage":
     ```markdown
     ## Local test scope

     Locally, run only the tests this change can affect; the full suite is CI's job.
     The scope is:

     - the files `la-affected-tests --base <base-branch>` prints (the PR's base
       branch once a PR exists, else the default branch): the tests this change
       added or changed, and every test whose imports reach a changed file;
     - whatever else you judge this change reaches: goldens, conformance cases and
       snapshots pinning changed output, tests reading changed data or config files,
       everything under a changed fixture or conftest;
     - every test CI reported failing on this PR.

     Run them with the repo's test runner (the one behind `la-config get
     commands.test`, keeping its usual options) narrowed to those files or test
     ids, leaving out printed files the runner does not collect as tests (helpers,
     fixtures). Never run the whole suite locally "to be safe"; a test missed here
     is caught by CI.
     ```
   - `pr-implement` Step 1: "Run the repo's test command (`la-config get commands.test`; if unset, the repo's
     documented full non-integration suite) after changes and fix any failures." → "After changes, run the tests
     in the `/la:pr` local test scope and fix any failures."
   - `pr-implement` Step 2: "Once the suite is green," → "Once the tests in scope are green,"
   - `pr-implement` merge paragraph: "re-run the local gates (full non-integration suite, conventions and type
     check) on the merged tree" → "re-run the local gates (the local test scope plus the tests covering every file
     the merge conflicted on, conventions and type check) on the merged tree"
   - `pr-review` local gates: "the repo's test command (`la-config get commands.test`; if unset, the repo's
     documented full non-integration suite) and the linter" → "the tests in the `/la:pr` local test scope (which
     includes every test CI reported failing) and the linter"
   - `pr-tests` Step 1, after "Tests should fail for the right reason (feature missing), not for setup reasons.":
     "Run the tests in the `/la:pr` local test scope to confirm that." (replaces the first approved sentence after
     Codex finding #18; user chose this wording)
   - Unchanged: `deterministic-refactor`, `arch-cleanup`, `make-diff-compliant` keep the full suite;
     `commands.test` keeps meaning the full suite.
7. **Push without asking; only opening a PR is gated** (user, approved wording):
   - `pr-review` Step 1, after the bold "Run this loop autonomously — fix findings and push fix batches without
     asking. …" paragraph: "Never ask before pushing to this PR's own branch: push as soon as a batch is ready.
     Only opening a PR needs my approval."
   - `pr/SKILL.md` stopping policy: "the standing **go-ahead gate before push/PR** (`pr-implement`): never push or
     open a PR without my explicit go-ahead;" → "the standing **go-ahead gate before opening a PR**
     (`pr-implement`): never open a PR without my explicit go-ahead; pushing this change's own branch needs none;"
   - `pr/SKILL.md` commit-at-end: "**Commit only** — pushing and opening the PR still need my explicit go-ahead
     (`pr-implement` Step 3 / the stopping policy above); the end-of-stage commit does not." → "**Commit only** —
     opening the PR still needs my explicit go-ahead (`pr-implement` Step 3 / the stopping policy above)"
   - `pr/SKILL.md` stage 3 summary: "then (with my go-ahead) commit, push, and open the PR." → "then commit and
     push, and (with my go-ahead) open the PR."
   - `pr/SKILL.md` stage detection: "awaiting my commit/push/PR go-ahead" → "awaiting my PR go-ahead"
   - `pr-implement` frontmatter description: "then with the user's explicit go-ahead commit, push, and open the PR"
     → "then commit, push and, with the user's explicit go-ahead, open the PR"
   - `pr-implement` Step 1: "The go-ahead gate in Step 3 governs **pushing** and **opening the PR**, not every
     local commit." → "The go-ahead gate in Step 3 governs **opening the PR** only."
   - `pr-implement` Step 3 title: "Ask me to push and open the PR" → "Push, then ask me to open the PR"
   - `pr-implement` Step 3 first sentence: "Once all tests pass AND both local gates are green, stop and ask me
     whether to push and open a PR (folding in any final commit of the implementation)." → "Once every test in
     scope passes AND both local gates are green, push the branch, then stop and ask me whether to open a PR
     (folding in any final commit of the implementation)."
   - `pr-implement` Step 3: "Intermediate local commits along the way were fine (Step 1), but **pushing** and
     **opening the PR** need my explicit go-ahead — do not do either on your own." → "Intermediate local commits
     along the way were fine (Step 1); push the branch when ready, but **opening the PR** needs my explicit
     go-ahead — never do it on your own."
   - `pr-tests`: "Do NOT push — pushing waits for the `pr-implement` go-ahead gate." → "Do NOT push — the first
     push happens in `pr-implement`."
   - `docs/how-it-works.md` stage 3 row: "…then commits, pushes and opens the PR on your go-ahead." → "…then
     commits and pushes, and opens the PR on your go-ahead."
8. **Python import extraction: `ast` and a lexical scan, edges unioned.** Options: `ast` only (a file its
   interpreter cannot parse — newer syntax, mid-edit — drops its edges and under-selects); lexical only (one
   path, over-selects on import-like text); `ast` with a fallback; every test on any parse failure (blows up the
   selection). Taken: both scanners on every file, union — neither needs to agree with the other. (user, after
   Codex finding #7)
9. **`--base` only, required, no PR positional.** Options: also a PR positional like `la-check-conventions`
   (adds `gh`/network; `pr-implement` has no PR yet). Taken: `--base` only; the skill names the base. (default)
10. **Other language via internal `--language L` with a JSON request on stdin and a schema-checked JSON
    response.** Options: the other twin re-running git (a second fetch; two change sets that could differ); the
    other twin printing final text (no identity check, sorting split). Taken: JSON both ways, render once.
    (default, refined by Codex finding #5)
11. **Untouched languages are never computed or probed.** Keeps a one-language change free of the other twin.
    (default)
12. **Other twin unreachable or failing → exit 2, empty stdout.** Options: degrade to own-language output with a
    warning (silent under-selection). Taken: exit 2, as `la-typecheck`. (default)
13. **Output unfiltered.** Printed test-glob matches include helpers, conftest and fixtures; filtering needs runner
    config, so the skill wording tells the agent to leave non-tests out. (default)
14. **TS edge targets: any in-repo file outside `node_modules`, real path for `node_modules` symlinks.** Covers
    JSON modules and workspace packages. (default, Codex finding #9)
15. **Deleted paths resolvable**: Python suffix matching includes them; TS through the virtual host layer
    (`fileExists`, `directoryExists`, `realpath`) plus the extension-candidate fallback. (default, Codex findings
    #3, #4)
16. **NUL-delimited git listings; non-UTF-8 or CR/LF paths exit 2 naming the path.** Options: skip such paths
    (silent under-selection); lossy decoding (twins diverge). (default, Codex finding #1)
17. **Unborn `HEAD`, missing base ref, not a git repo → exit 2 via the shared git error.** Conflicted paths count as
    changed; submodule gitlinks carry no source extension and are ignored. (default, Codex finding #8)
18. **Per-file nearest-tsconfig project cache** rather than the arch-check's per-root selection. (default, Codex
    finding #10)
19. **New all-specifiers TS scan**, `runtimeSpecifiers` unchanged for `la-arch-check`. (default, Codex finding #11)
20. **Narrow `lang` API (edges over graph paths + deleted paths).** (default, Codex finding #12)
21. **Git texts renamed `conventions.*` → `changes.*`, same wording.** (default)
22. **Forwarded paths validated as repo-relative POSIX** (no absolute, `.`/`..`, backslash segments) by the
    schema. (codex, finding #6)
23. **Additional test coverage** for Python and TS resolution, git states and twin determinism. (codex, findings
    #13–#16)
24. **Decisions log expanded with options and rationale.** (codex, finding #19)
25. **Version bump stays out of scope.** rejected (codex, finding #17): the minor-bump rule applies on the release
    PR only (`test_the_rule_is_not_applied_once_the_version_is_tagged`), and the issue excludes a release.
26. **Relative-import off-by-one for `__init__.py`.** rejected (codex, finding #2, first half): level 1 is the
    importer's own directory for `__init__.py` and ordinary modules alike. Its second half (probing imported
    names and the package `__init__.py` for `from . import x`) is folded in. (codex)

## Risks / Trade-offs

- [Suffix matching over-selects on common names (`utils`, `helpers`)] → accepted: extra local tests, never a miss.
- [Lexical scan matches import-like text in strings/docstrings] → accepted: over-selection only.
- [Dynamic imports (`importlib`, computed `import()`), subprocess-invoked code, data files] → not exact, left to
  the agent's judgement by the skill wording; CI runs the full suite.
- [Large repos: every source file parsed per run] → one pass per file, seconds; no caching state to go stale.
- [The TS virtual host diverging from the real resolver on deleted paths] → the extension-candidate fallback
  catches what the resolver misses; conformance cases pin deleted targets behind aliases and directory indexes.
- [Predicted `model.c4` arrows differ from the measured imports] → brought back to the user before any change.
