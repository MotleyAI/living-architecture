---
name: fetch-review-comments
description: Use when the user asks to fetch / list / read / show review comments or unresolved review threads on a GitHub PR, from CodeRabbit or anyone else. Pulls every unresolved thread, review body and PR conversation comment not written by the logged-in user, each marked answered or not, plus CodeRabbit's review-summary nitpicks and outside-diff comments.
---

**Preflight:** run `la-doctor --plugin <this skill's base directory>` once per session before using any `la-*` or `trmv-*` command; if it fails, stop and show the user its output. If `la-doctor` is not found, or reports the la tools older than the plugin, stop and give the user the install command at this plugin's `version` (in its `.claude-plugin/plugin.json`): `uv tool install living-architecture==<version> --with-executables-from type-rename-move` in a Python repo, `npm install -g living-architecture@<version> type-rename-move@<version>` in a TS/JS repo.

# Fetch review comments from a PR

## How to run

```bash
la-fetch-review-comments <PR_NUMBER> [--repo OWNER/REPO]
```

Works in any repo; it does not read `living-architecture.yaml`.

- `<PR_NUMBER>` — required, the PR number.
- `--repo OWNER/REPO` — optional; defaults to the repo of the current git directory.

## Output

- **Markdown to stdout** — one section per unresolved inline thread (URL, file:line, resolved/outdated, answered, each comment with its author), then `## Review bodies`, `## Conversation comments`, `## CodeRabbit review-summary nitpicks` and `## CodeRabbit outside-diff-range comments`.
- **JSON file** — `${TMPDIR:-/tmp}/review-comments-<pr>-<utc-timestamp>.json`, path on the last line after `JSON: `:

  ```json
  {"pr": 63, "repo": "owner/name", "threads": [...], "reviews": [...], "comments": [...], "nitpicks": [...], "outside_diff": [...]}
  ```

Comments by the logged-in `gh` user are left out, since those are your own replies. CodeRabbit's review bodies appear only through its nitpick and outside-diff sections. A thread is `answered` when its last comment is yours; a review body or conversation comment is `answered` when a later conversation comment of yours starts with the line `Re: <its URL>` (what `la-reply-to-pr-thread` writes).

## Steps

1. Run it with the PR number the user gave (else `gh pr view --json number -q .number`).
2. Summarise the Markdown for the user (counts per section, files, unanswered comments); re-parse the JSON for structured data.
3. **Never** call any "resolve" mutation. Only read.

## Why this skill

`isResolved` needs `gh api graphql`; review bodies and conversation comments need two more REST calls; answered needs the logged-in user. This bundles all of it. Always use it instead of hand-rolling `gh api` queries.
