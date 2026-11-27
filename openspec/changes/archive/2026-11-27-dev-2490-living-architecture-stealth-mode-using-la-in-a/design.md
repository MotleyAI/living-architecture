## Context

See proposal.md for the motivation. Since 0.14.0 the repo ships two packages: trmv (`trmv-*`, config `trmv.yaml`,
typecheck, change sets, language adapters) and la (`la-*`, config `living-architecture.yaml`), and la depends on trmv,
never the reverse (system principle 5). trmv already resolves which config file a command reads, and already knows
`living-architecture.yaml` by name. Base refs are resolved in `trmv.changes` as `origin/<base>` only. Inline
`ALLOW(<rule>): <reason>` waivers are la's own spelling. `la-reply-to-pr-thread` and `la-reply-invalid-coderabbit` are
bundled scripts.

Applicable principles (`architecture/system.arc42.md`):
1. Twins: every new behaviour ships in both twins with conformance cases.
2. Shared contract: leak tokens, path registries, schemas (stealth keys, waiver ledger), messages, environment
   directories and fingerprint files all live in `shared/la/` or `shared/trmv/`.
3. Language-specific code only in `trmv.lang` and `trmv.refactor`: preparing a checker environment for another
   revision lives in `trmv.lang`.
4. Only configured commands run: the merge-base check runs the configured checker command.
5. trmv never depends on la: the config resolver is trmv's; la uses it through the existing `la -> trmv` arrow.

## Goals / Non-Goals

**Goals:**
- One config resolver (trmv) that finds root and stealth config files for both packages.
- Nothing la- or trmv-specific in the working tree, the pushed refs or posted text of a stealth repo.

**Non-Goals:**
- The architecture model in stealth mode (approved scope cut: a model that is not versioned with the code cannot
  stay exactly true across branches).
- Converting a repo between stealth and normal mode.
- Git hooks.
- Scrubbing history already pushed.
- Pruning the waiver ledger automatically.
- A leak check for trmv-only stealth repos (the check lives in la).

## Decisions

The decisions log of the planning interview, in order:

1. **Stealth location: the git common directory** — one config file in `<git-common-dir>`, its presence is the
   switch. Rejected: a stealth flag in a repo-root `living-architecture.yaml` excluded from git and copied between
   the main checkout and worktrees by `/la:pr` (copies drift, only `/la:pr` copies so other commands see no config in
   a fresh worktree, no main checkout in a bare-repo layout). (user)
2. **Stealth means `architecture: false`** — approved scope cut against the issue. Rejected: a private model in the
   stealth directory, shared by all branches, which turns model-truth red on whichever branch did not change the
   structure. (user)
3. **No plan on any tracker in stealth, Linear included.** Rejected: keeping the Linear finalized-plan comment and
   using a private plan file only for GitHub/none trackers. (user)
4. **OpenSpec stays an independent choice** — the repo's tracked `openspec/` when it has one, else a private OpenSpec
   store (`openspec store`, `--store <id>`) in the stealth directory; `openspec: false` keeps the plan in
   `<C>/living-architecture/plans/<CHANGE_ID>.md`. This supersedes the typed brief's "stealth implies no OpenSpec
   unless there already is an openspec folder in git". Rejected: forcing OpenSpec on in stealth. (user)
5. **Skill rules plus a deterministic leak check.** Rejected: skill rules only. (user)
6. **Typecheck baseline from the merge-base**, cached per commit. Rejected: a per-worktree baseline in the tree hidden
   by `.git/info/exclude` (needs `--write-baseline` per worktree, would hide a baseline the repo later adopts, stale
   when a worktree changes branch). (user)
7. **The leak check is its own node `la.leaks`** with spec `stealth-leaks`. Rejected: folding it into `la.review`,
   which would gain `config` and `changes` dependencies unrelated to review shims. (user)
8. **Stealth waivers live in a ledger** in the stealth directory, matched by path, rule and line text. Rejected: no
   waivers in stealth (forces turning a rule off repo-wide for a line you must not change); purging inline waivers at
   archive time (they are already pushed by then, and rewriting history is ruled out). (user)
9. **No tracker writes of any kind in stealth** (no comments, no state changes, no "Done on merge"), derived from 3.
   (default)
10. **`living-architecture.local.yaml` is a config error in stealth**: the stealth config is already per person.
    (default)
11. **A root and a stealth config together is an error naming every file present.** (default)
12. **Environment directories are linked into the merge-base worktree** so the checker resolves imports as in the
    working tree. (default)
13. **Leak tokens match whole and case-insensitively; command names come from the CLI contracts**, so new commands
    are covered without editing the list. (default)
14. **`la:pr` stage detection and rehydration read `<C>/living-architecture/plans/<CHANGE_ID>.md`** in stealth with
    `openspec: false`; `pr-plan` writes it; no stage searches for or posts a tracker plan comment. (codex)
15. **Both reply commands scan the body**; skills never post through raw `gh` or an MCP tool in stealth; the PR title
    and body pass `la-leak-check --text -` before `gh pr create`. (codex)
16. **The branch name is scanned**; merge commits are part of the scanned range. (codex)
17. **The merge-base cache key includes a fingerprint** of the configured command, the trmv version and the
    language's fingerprint files. (codex)
18. **Environment preparation lives in `trmv.lang`**, diagnostics are keyed repo-relative, a checker failure at the
    merge base exits 2 naming the commit. Kept: linking environment directories, the only way `tsc` resolves
    `node_modules` for a tree outside the checkout. (codex)
19. **Common-dir resolution** uses `git rev-parse --show-toplevel` and `--path-format=absolute --git-common-dir`; a
    submodule has its own stealth directory. (codex)
20. **Bare repos work through their linked worktrees; outside git there is no stealth lookup.** (codex)
21. **The doctors' registry covers both baselines and an untracked `openspec/`**, read NUL-safe, with a golden for each
    state (tracked, staged, untracked, ignored, absent). (codex)
22. **No doctor check on `.gitignore` lines.** The leak check blocks any added line naming an la path, and lines the
    repo already has are not the user's. Changes the approved §3. (codex)
23. **Two token groups**: core tokens can never be allowed; only waivable ones go in `leaks.allow`. Adversarial cases
    for case, path, hyphen and Markdown variants. (codex)
24. **Ledger normalization**: trailing CR removed, leading and trailing whitespace trimmed. (codex)
25. **Conformance harness steps** for linked worktrees, `.git/info/exclude` and submodules. (codex)
26. **The private store is created with `openspec store setup --init-git`**; stage-end commits name only that change's
    folder paths; a commit that hits another worktree's `index.lock` is retried. (codex)
27. **Every `--base` accepts a remote-tracking ref** (`<remote>/<branch>` when `<remote>` is a configured remote),
    through one shared resolver; skills pass the PR's real base remote. Rejected: accepting it only in the new stealth
    commands (two resolutions that must agree by hand); leaving forks wrong. (user)
28. **The plan follows the 0.14.0 split**: typecheck and base resolution in trmv, leak check in la; tokens include
    every `trmv-*` command, `/trmv:`, `type-rename-move`, `trmv` and `trmv.yaml`. (default)
29. **Stealth covers trmv-only repos too**: `<C>/trmv/trmv.yaml`, `/trmv:init` offers stealth, `trmv-doctor` gets its
    registry check. Rejected: trmv reading only la's stealth config. (user)
30. **Branch content is checked as of `HEAD`**: the net diff from the merge base, before every push; a token only in an
    intermediate commit is accepted, since leak tokens are not secrets. Rejected: scanning each commit, squashing
    before each push. (user)

Rejected Codex findings:
- **Always use a private store, even when the repo tracks `openspec/`** — rejected (codex): the user's brief keeps the
  repo's own OpenSpec, and a change folder in a repo that uses OpenSpec is that repo's practice, not a trace.
- **Fail on a waiver entry matching several lines** — rejected (codex): identical lines with the same rule in one file
  share a reason; the ledger matches by text on purpose.

Implementation notes:
- The resolver returns the config file and whether it is a stealth one; `stealth` is derived, never parsed.
- `openspec_store` id: `la-` + first 12 hex digits of SHA-256 of the absolute `<C>/living-architecture/` path.
- The reply scripts pipe every body through `la-leak-check --text -` before any `gh` call and stop on a nonzero exit;
  `la-leak-check` decides stealth by whether a stealth config file is present, before reading any config.
- Skill edits: each exact wording is shown to the user and approved before the edit (see tasks.md).

## Risks / Trade-offs

- [A paraphrase slips past the token list] → the skills' text rule stays; the list is in `shared/` and grows with
  real slips.
- [The merge-base check costs a second checker run] → cached per merge-base commit and fingerprint, shared by every
  worktree.
- [Linked environment directories differ from the merge base's lockfiles] → errors caused by dependency changes show
  as new errors; the fingerprint recomputes when lockfiles change.
- [Archive in a private store lands in the shared corpus before the PR merges] → the store is a git repo; a revert
  undoes an abandoned change's archive.
- [A branch named `<remote>/<x>` on origin when `<remote>` is also a remote] → the remote reading wins; documented.

## Migration Plan

None: stealth is opt-in and every existing repo keeps its behaviour (no config file in the git common directory).
