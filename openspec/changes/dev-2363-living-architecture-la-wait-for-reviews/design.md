## Context

See proposal.md (Why) and the `review-detection` delta for the required behaviour. Everything here is in the `la`
package of the split repo: `shared/la/scripts/` holds the four bash scripts, both twins run them through the
passthrough shim, and `scripts/sync-shared` refreshes `python/la/src/living_architecture/contract/data/` and
`node/la/src/contract/data/`. So the twins agree by construction, and the `conformance/la/` corpus pins the output.

Structural causes:
1. The watcher's only terminal signals were "gate clear" and "timeout". A PR state that guarantees the gate never
   clears went unobserved. The fix sits where PR state is read each poll (the snapshot), not in a side read, so the
   reported conflict always belongs to the HEAD that poll read.
2. "CodeRabbit vs everyone else" was a split that the watcher and the fetcher each made by hand. Both now apply ONE
   rule: every comment not by the logged-in `gh` user. CodeRabbit is just a login that the skill routes on.

Principles that apply (`architecture/system.arc42.md`): 1 (twins; the corpus decides), 2 (texts and surfaces come
only from the shared contracts: exit map, help, script texts in `shared/la/`), 4 (no target-repo code runs). 5 (`dr`
never depends on `la`) is untouched. No model or arc42 edits are needed. The spec delta attaches to the existing
`review-detection`, owned by `python.la.review`.

## Goals / Non-Goals

**Goals:**
- One snapshot read per poll gives the HEAD, the rollup and `mergeable`.
- One comment rule shared by the watcher and the fetcher. Each comment endpoint is read once per poll.
- Answered state is computed from GitHub alone, so it holds across machines and sessions.

**Non-Goals:**
- No version bump or release in this PR. The release is DEV-2366.
- No edit of the user's global `~/.claude/CLAUDE.md`. The replacement wording is a comment on DEV-2366.
- No alias for `la-fetch-coderabbit-threads`.

## Decisions

1. Read `mergeable` inside the existing snapshot call (`rb_snapshot`: `gh pr view --json
   headRefOid,mergeable,statusCheckRollup`), not in a separate per-poll read. One consistent read pairs the conflict
   with the HEAD it is reported for: no race, and one call fewer. `la-pr-reviewers` shares the helper and ignores the
   field. (default)
2. A conflicting poll prints only `merge-conflict` (after `head-moved`), then exits 4 before any other read, item or
   state write. The alternative was printing the poll's other items first. This follows the issue's "one item, exit
   at once". Unprinted items are not saved, so the next run prints them and nothing is lost. (codex; replaced the
   default "other items first")
3. `merge-conflict` is printed on every detection, not keyed or saved, like `head-moved`. The alternative was keyed
   by SHA. This way every exit-4 run explains itself on stdout. (user)
4. No version bump in this PR (the issue: "Release and pin bump follow the repo's normal flow"). (default)
5. Extension: watch, fetch and triage every reviewer's comments, not just CodeRabbit's. (user)
6. Which comments: monitor everything except the logged-in user's own comments, and let the LLM decide what gets a
   reply. It replies to any comment asking for a change or asking a question, on any channel, and never to a status
   update. The rejected options were all authors on all surfaces with replies forced, bots excluded from
   conversation comments, and humans only. (user)
7. Watcher items: one author-tagged set for every author (`review-comment` / `review` / `pr-comment <login> <url>`),
   replacing `coderabbit-comment` / `coderabbit-review`. The alternative kept the CodeRabbit items next to new ones,
   which meant two hand-kept complementary filters. Cost: on PRs watched across the upgrade, CodeRabbit's items
   reprint once. (user)
8. Self is the logged-in `gh` user (`gh api user`), whose comments are our own replies. In the watcher, an unknown
   self makes the comment sources failed reads for that poll, retried on the next. In the fetcher, it fails the
   command. (default)
9. Fetch command: generalize the existing fetcher under the one rule and rename it `la-fetch-review-comments`. The
   alternatives were keeping the old name, or adding a second fetcher. (user) No alias: the plugin and tools release
   together, and the only outside caller is the user's global CLAUDE.md, which the user updates. (user)
10. CodeRabbit's review bodies stay out of `reviews`, because their content is already parsed into `nitpicks` /
    `outside_diff`. (default)
11. Replies to review bodies and conversation comments are a `Re: <url>` conversation comment, and answered is
    detected on GitHub. The alternatives were no tracking, or local state. (user)
12. Replies to comments not from CodeRabbit are proposed and posted only after the user's OK. CodeRabbit replies stay
    autonomous. (user)
13. Skill and docs wording as quoted under "Approved wording" below. (user, approved wording)
14. `answered` needs a reply whose first line is exactly `Re: <url>`. Merely containing the URL doesn't count, since
    an incidental mention would falsely answer. (codex)
15. `rb_coderabbit` reuses the poll's conversation comments (`la-pr-reviewers` still has it read them), so every
    comment endpoint is read once per poll. (codex)
16. A missing author (a deleted account) is `ghost`, never self. (codex)
17. Pagination tests cover every generalized list and both GraphQL cursors. (codex)
18. The rewritten settle requirement also documents CodeRabbit's existing `skipped` outcome: exit 3, and the
    re-trigger command only for rate limited or paused. This is spec text only and brings the spec in line with the
    code and the `shim-wait-for-reviews-skipped*` cases. (user)
19. Local Sonar pre-check before every push, in pr-review and pr-implement, on each changed production source file;
    when the tool fails or is unavailable, it is ignored. (user)
20. Standalone process-reviews reports a merge conflict in its plan instead of merging. (user; CodeRabbit)
21. Approved reply drafts are posted at once when no push follows. (user; CodeRabbit)

## Approved wording

### Merge conflict (user, approved wording)
- process-reviews Step 0a + 0b item list: the last bullet `- \`head-moved <old> <new>\`.` becomes
  `- \`head-moved <old> <new>\`;` followed by `- \`merge-conflict <sha>\`: the PR conflicts with its base, so CI will not run.`
- process-reviews exit sentence ends: `…, 3 when CodeRabbit was rate limited, paused or skipped its review on HEAD, once the checks finish, and 4 at once on a merge conflict.`, followed by a new paragraph: `**Merge conflict** (exit 4): stop waiting. Invoked from \`la:pr-review\`, fetch and merge \`origin/<base>\` (never rebase), re-run the local gates, push, and re-arm the watch; run standalone, put the conflict at the top of the plan instead.`
- pr-review Step 1 loop item 3, right after "…whole batch.": `Before every push, fetch and, when \`origin/<base>\` is not an ancestor of HEAD, merge it (never rebase) and re-run the local gates.`

### Every reviewer's comments (user, approved wording)
process-reviews/SKILL.md:
- a. Frontmatter description: `triages each new failed CI check, CodeRabbit comment and finished Sonar analysis` → `triages each new failed CI check, review comment and finished Sonar analysis`; `fetches unresolved threads from all three code-review sources` → `fetches every review comment and unresolved thread from every reviewer, Sonar's findings`.
- b. Item bullet `- \`coderabbit-comment <url>\` / \`coderabbit-review <url>\`: a new CodeRabbit thread, reply, or review body;` → `- \`review-comment <login> <url>\` / \`review <login> <url>\` / \`pr-comment <login> <url>\`: a new inline comment (thread or reply), review body, or PR conversation comment by anyone but you;`
- c. `` `la-fetch-coderabbit-threads <PR>` for a CodeRabbit item (triage only the named comment or review) `` → `` `la-fetch-review-comments <PR>` for a comment item (triage only the named comment) ``
- d. `triage whatever no event named: edited CodeRabbit comments, and older threads that need a reply.` → `triage whatever no event named: edited comments, and older threads and comments that need a reply.`
- e. Step 1 bullet start → `- **Review comments** — run \`la-fetch-review-comments <PR>\` (see the \`la:fetch-review-comments\` skill).` (rest of the bullet kept). After its `threads[]` sentence add: `` `reviews[]` (review bodies, CodeRabbit's excluded) and `comments[]` (conversation comments) carry `{author, url, createdAt, body, answered}`; every thread also carries `answered`. ``
- f. Step 2: the `source` enum gains `"review"` (a comment not from CodeRabbit); its `ref` is the comment URL.
- g. Step 3, a bullet after the CodeRabbit / Sonar / Codex one: `- **Review comments not from CodeRabbit** — a status update (a bot's summary, gate, coverage or deploy report) is no finding: skip it. Any other comment asking for a change is validated like a CodeRabbit comment; a question is neither valid nor invalid, it needs an answer.`
- h. Step 4, a new subsection before `#### CodeRabbit (invalid)`:
  ```
  #### Review comments not from CodeRabbit

  Draft a reply for every comment with `answered: false` that asks for a change or asks a question, whichever channel it came on; never for a status update. A fix's reply names the commit that fixed it; an invalid request's reply says why. Never post a draft unasked: list it in the Step 5 plan (invoked from `la:pr-review`, return it with the triaged list), and post it with `la-reply-to-pr-thread <url>` only after the user's OK.
  ```
- i. Step 5 header line: `` `Triaged: <V> valid / <I> invalid (<C> CodeRabbit + <R> other reviewers + <S> Sonar + <X> Codex + <CI> CI)` ``. After the per-issue bullet: `- A **Proposed replies** section: each draft from Step 4 with its comment URL, for the user to approve or edit.`
- j. `<discussion-url-from-la-fetch-coderabbit-threads-output>` → `<discussion-url-from-la-fetch-review-comments-output>`.
- k. "When NOT to use this skill": both `la:fetch-coderabbit-threads` → `la:fetch-review-comments`.

pr-review/SKILL.md, Step 1 loop item 3, after the merge sentence: `Reply drafts \`/la:process-reviews\` returned go to me as one approval question before that push (or before reporting green when no push follows); post the approved ones with \`la-reply-to-pr-thread\` once the push is up, or at once when no push follows.`

fetch-review-comments/SKILL.md (replaces fetch-coderabbit-threads/SKILL.md), whole file (the indented blocks are
fenced code blocks in the file):
```
---
name: fetch-review-comments
description: Use when the user asks to fetch / list / read / show review comments or unresolved review threads on a GitHub PR, from CodeRabbit or anyone else. Pulls every unresolved thread, review body and PR conversation comment not written by the logged-in user, each marked answered or not, plus CodeRabbit's review-summary nitpicks and outside-diff comments.
---

**Preflight:** run `la-doctor --plugin <this skill's base directory>` once per session before using any `la-*` or `dr-*` command; if it fails, stop and show the user its output.

# Fetch review comments from a PR

## How to run

    la-fetch-review-comments <PR_NUMBER> [--repo OWNER/REPO]

Works in any repo; it does not read `living-architecture.yaml`.

- `<PR_NUMBER>` — required, the PR number.
- `--repo OWNER/REPO` — optional; defaults to the repo of the current git directory.

## Output

- **Markdown to stdout** — one section per unresolved inline thread (URL, file:line, resolved/outdated, answered, each comment with its author), then `## Review bodies`, `## Conversation comments`, `## CodeRabbit review-summary nitpicks` and `## CodeRabbit outside-diff-range comments`.
- **JSON file** — `${TMPDIR:-/tmp}/review-comments-<pr>-<utc-timestamp>.json`, path on the last line after `JSON: `:

      {"pr": 63, "repo": "owner/name", "threads": [...], "reviews": [...], "comments": [...], "nitpicks": [...], "outside_diff": [...]}

Comments by the logged-in `gh` user are left out, since those are your own replies. CodeRabbit's review bodies appear only through its nitpick and outside-diff sections. A thread is `answered` when its last comment is yours; a review body or conversation comment is `answered` when a later conversation comment of yours starts with the line `Re: <its URL>` (what `la-reply-to-pr-thread` writes).

## Steps

1. Run it with the PR number the user gave (else `gh pr view --json number -q .number`).
2. Summarise the Markdown for the user (counts per section, files, unanswered comments); re-parse the JSON for structured data.
3. **Never** call any "resolve" mutation. Only read.

## Why this skill

`isResolved` needs `gh api graphql`; review bodies and conversation comments need two more REST calls; answered needs the logged-in user. This bundles all of it. Always use it instead of hand-rolling `gh api` queries.
```
The `answered` sentence above was re-approved after Decision 14 (codex), which narrowed it to a first line of
exactly `Re: <url>`. (user, approved wording)

reply-to-pr-thread/SKILL.md:
- a. Description: `Use when the user asks to reply / comment on a PR review thread, review body or conversation comment (CodeRabbit or anyone), OR when posting a reasoning/explanation reply tagging @coderabbitai for a thread you've classified as invalid. Body is read from stdin.`
- b. After the "How to run" bullets: `- A review-body URL (\`#pullrequestreview-<ID>\`) or conversation-comment URL (\`#issuecomment-<ID>\`) cannot be threaded: the command posts a PR conversation comment whose first line is \`Re: <url>\`, then the body. \`la-fetch-review-comments\` reads that line to mark the comment answered.`
- c. Step 1: `` From the `la-fetch-coderabbit-threads` output, that's the URL printed in `Comment 1 — coderabbitai`. `` → `` From the `la-fetch-review-comments` output, that's the URL printed under the comment. ``

Docs:
- `docs/commands.md`: the fetch row becomes ``| `la-fetch-review-comments <PR>` | Unresolved threads, review bodies and conversation comments from every reviewer, each marked answered; CodeRabbit's nitpicks and outside-diff comments |``, and the `la-wait-for-reviews` row says "review comment" in place of "CodeRabbit comment".
- `docs/skills.md`: ``| `la:fetch-review-comments` | Every review comment and unresolved thread on a PR, from any reviewer |``.

### Sonar pre-check (user, approved wording)
- pr-review Step 1, the local-gates bullet `(Sonar on the PR) local Sonar pre-check: …` becomes:
  `- local Sonar pre-check, before every push: \`mcp__sonarqube__analyze_code_snippet\` on each changed production source file (single-file only, a pre-filter, NOT a substitute for the pushed Sonar gate); fix its findings like any gate's. If the tool fails or is unavailable, ignore it;`
- pr-implement Step 2, a paragraph after **Type check.**:
  `**Sonar pre-check.** Run \`mcp__sonarqube__analyze_code_snippet\` on each changed production source file and fix its findings. If the tool fails or is unavailable, ignore it.`

## Risks / Trade-offs

- [The command and item names change] → Release notes on DEV-2366, the CLAUDE.md wording on DEV-2366, and every
  skill in this repo updated in the same change.
- [Every comment endpoint is now read on every poll, even with no CodeRabbit] → One read per list per poll,
  paginated. That's the same calls the CodeRabbit path already made, now made unconditionally.
- [A reply posted by hand without the `Re: <url>` line is not seen as an answer] → A reply is proposed again. The
  user can drop that proposal, or post the reply through `la-reply-to-pr-thread`.
- [Status bots add one item and one triage row each] → Each is printed once, and triage skips status updates.
