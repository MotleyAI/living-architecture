## Why

GitHub runs no CI on a PR that conflicts with its base branch. `la-wait-for-reviews` never reads mergeability, so on
a conflicted PR its gate never clears: it waits out the 30-minute timeout and the pr-review loop re-arms it. Also, only
CodeRabbit's comments are watched, fetched and answered, so comments by people and by other review bots are never seen.

## What Changes

- `la-wait-for-reviews` reads the PR's `mergeable` state in its per-poll snapshot. On `CONFLICTING` it prints only
  `merge-conflict <sha7>` and exits 4 at once. `UNKNOWN` keeps polling.
- `la-wait-for-reviews` prints every comment not written by the logged-in `gh` user as author-tagged items
  (`review-comment` / `review` / `pr-comment <login> <url>`), on every PR. **BREAKING:** these replace
  `coderabbit-comment` and `coderabbit-review`.
- **BREAKING:** `la-fetch-coderabbit-threads` is renamed `la-fetch-review-comments`, with no alias and no
  `--all-authors`. It returns every unresolved thread, review body and conversation comment not by the logged-in
  user, each marked `answered`, plus CodeRabbit's nitpick and outside-diff sections.
- `la-reply-to-pr-thread` also replies to review bodies and conversation comments, posting a `Re: <url>`
  conversation comment.
- Skills: process-reviews handles merge conflicts and triages every reviewer's comments, and drafts replies to
  comments not from CodeRabbit for the user's OK. pr-review merges the base before every push and puts reply drafts
  to the user. The fetch-coderabbit-threads skill becomes fetch-review-comments. reply-to-pr-thread documents the new
  URL forms.

## Capabilities

### New Capabilities

### Modified Capabilities
- `review-detection`: the watcher's merge-conflict exit, its comment items for every author, the renamed fetch
  command with answered detection, and replies to review bodies and conversation comments.

## Impact

- `shared/la/scripts/` (wait-for-reviews.sh, review-bots.bash, fetch-review-comments.sh renamed from
  fetch-coderabbit-threads.sh, reply-to-pr-thread.sh), `shared/la/cli.yaml`, and both twins' snapshots.
- The Python and npm entry points for the renamed command (`python/la/pyproject.toml`, `node/la/package.json`).
- The `conformance/la/` corpus and `python/la/tests/`.
- `plugin/la/skills/` (process-reviews, pr-review, fetch-review-comments, reply-to-pr-thread), `docs/commands.md`,
  `docs/skills.md`.
- The user's global CLAUDE.md names the old fetch command. Its replacement wording is tracked on the release issue.
