## Why

A `pr-review` remote sweep blocks on `la-wait-for-reviews` until every CI check and CodeRabbit have settled on
HEAD, 5–30 minutes. A failure known early waits for the slowest source, and when the wait stops early (a session
ends, a rate limit) feedback already on the PR goes untriaged. The watcher reports only a whole-gate verdict, so
which items are new is left to the agent's memory, which compaction, a session end or a Monitor expiry erases.

## What Changes

- `la-wait-for-reviews` polls every source once a minute in one loop and prints one stdout line per new item:
  `ci-failed`, `coderabbit-comment`, `coderabbit-review`, `sonar-done`, `coderabbit-settled`, `head-moved`. Each
  item is printed once, even across runs: the printed keys persist per PR in the worktree's git dir. Progress lines
  move to stderr. The hard-coded 30 s CodeRabbit poll is dropped. Exit codes keep their meaning; exit 3 (rate
  limited / paused) comes once the checks are terminal.
- `la-fetch-failed-pr-checks --check X` keeps only the failed checks whose details URL or name equals `X`.
- The `process-reviews` and `pr-review` skills arm the watcher with Monitor, triage each item as it arrives, fix
  valid items in the working tree while the watch runs, and push once after it exits and the local gates converge.

## Capabilities

### New Capabilities

### Modified Capabilities
- `review-detection`: `la-wait-for-reviews` reports each new item once, polls every source on one cadence, and
  defers exit 3 until the checks are terminal.
- `failed-pr-checks`: `--check` keeps one check.

## Impact

- `shared/scripts/wait-for-reviews.sh`, `shared/scripts/fetch-failed-pr-checks.sh`, `shared/cli.yaml` (help texts),
  the twins' vendored `shared/` snapshots.
- `plugin/skills/process-reviews/SKILL.md`, `plugin/skills/pr-review/SKILL.md`.
- Conformance: new `shim-wait-for-reviews-*` and `shim-fetch-failed-pr-checks-*` cases; every existing
  `shim-wait-for-reviews-*` golden is re-blessed (progress moves to stderr). `python/tests/test_review_scripts.py`.
- New local state: `$(git rev-parse --git-path la/reviews/<owner>/<repo>/<PR>.json)`.
