## ADDED Requirements

### Requirement: la-wait-for-reviews stops on a merge conflict
`la-wait-for-reviews` SHALL read the PR's `mergeable` state in the same read as the head commit and its status
rollup, on every poll: while the gate is pending and during the CodeRabbit settle after it cleared. When that read
succeeds and `mergeable` is `CONFLICTING`, the command SHALL print `merge-conflict <sha7>` right after that poll's
`head-moved` line (if any), report on stderr that the PR conflicts with its base and the base must be merged, and
exit 4 at once. It SHALL do this without reading any other source, printing or saving any other item of that poll,
and before the gate timeout and every settle exit. `MERGEABLE`, `UNKNOWN`, a missing or non-string `mergeable`, and a
failed read SHALL NOT count as a conflict. The `merge-conflict` line SHALL be printed on every detection and never
saved in the state file.

#### Scenario: Conflict while a check runs
- **WHEN** a CheckRun is in progress and `mergeable` is `CONFLICTING`
- **THEN** stdout has only `merge-conflict <sha7>`, stderr reports the conflict, and the command exits 4 after the first poll

#### Scenario: Conflict during the settle
- **WHEN** `LA_WAIT_POLL_SECONDS` is `0`, the gate is clear, CodeRabbit is on the PR without evidence for the head commit, and `mergeable` is `MERGEABLE` on the first poll and `CONFLICTING` on the second
- **THEN** the command prints `merge-conflict <sha7>` and exits 4 after the second poll

#### Scenario: Unknown keeps polling
- **WHEN** `mergeable` is `UNKNOWN` and the rollup is clear, with no CodeRabbit on the PR
- **THEN** the command prints no `merge-conflict` line and exits 0

#### Scenario: Unknown, then conflicting
- **WHEN** `LA_WAIT_POLL_SECONDS` is `0`, a CheckRun is in progress on both polls, and `mergeable` is `UNKNOWN` on the first poll and `CONFLICTING` on the second
- **THEN** the command prints `merge-conflict <sha7>` and exits 4 after the second poll

#### Scenario: A conflict prints no other item
- **WHEN** the rollup has a failed CheckRun `tests` and `mergeable` is `CONFLICTING`
- **THEN** stdout has only `merge-conflict <sha7>`, and a later run on a mergeable PR prints the `ci-failed` line

#### Scenario: Head moved onto a conflict
- **WHEN** `LA_WAIT_POLL_SECONDS` is `0` and the second poll sees a new head commit with `mergeable` `CONFLICTING`
- **THEN** stdout ends with `head-moved <old7> <new7>` then `merge-conflict <new7>`, and the command exits 4

#### Scenario: A conflict beats the gate timeout
- **WHEN** `LA_WAIT_GATE_TIMEOUT` is `0`, a CheckRun is in progress, and `mergeable` is `CONFLICTING`
- **THEN** the command exits 4, not 1

#### Scenario: A second run reports the conflict again
- **WHEN** a run exited 4 on a conflict and a second run sees the same PR state with the same state file
- **THEN** the second run prints `merge-conflict <sha7>` again and exits 4

#### Scenario: Missing mergeable state
- **WHEN** the snapshot has no `mergeable` field and the rollup is clear, with no CodeRabbit on the PR
- **THEN** the command prints no `merge-conflict` line and exits 0

### Requirement: la-fetch-review-comments lists every reviewer's comments
`la-fetch-review-comments <PR> [--repo OWNER/REPO]` SHALL list every comment on the PR that the logged-in `gh` user
did not write, from any author, bots included. An author missing from GitHub's data (a deleted account) SHALL be
`ghost` and never the logged-in user. It SHALL print Markdown on stdout and write the same data as JSON
`{pr, repo, threads, reviews, comments, nitpicks, outside_diff}` to a file under `${TMPDIR:-/tmp}`, naming the file on
the last stdout line after `JSON: `:
- `threads`: every unresolved review thread with at least one comment not by the logged-in user, with all its
  comments; a thread is `answered` when its last comment is by the logged-in user.
- `reviews`: every review with a non-whitespace body by neither the logged-in user nor CodeRabbit, and
  `comments`: every PR conversation comment not by the logged-in user; each with its author, URL, creation time,
  body and `answered`. A review or conversation comment is `answered` when a later conversation comment by the
  logged-in user has `Re: <its URL>` as its first line.
- `nitpicks` and `outside_diff`: the nitpick and outside-diff sections of CodeRabbit's review bodies.
Every list SHALL be read across all its pages. `--all-authors` SHALL be a usage error. A failed `gh` read, including
of the logged-in user, SHALL fail the command.

#### Scenario: Every author but the logged-in user
- **WHEN** the logged-in user is `me` and the PR has an unresolved thread by `alice`, a review body by `copilot-pull-request-reviewer[bot]`, a review body by `coderabbitai[bot]`, conversation comments by `bob` and `sonarqubecloud[bot]`, and a review body and a conversation comment by `me`
- **THEN** `threads` holds alice's thread, `reviews` holds only Copilot's review, and `comments` holds bob's and Sonar's comments

#### Scenario: Thread answered by its last comment
- **WHEN** one unresolved thread ends with a reply by the logged-in user and another ends with a reply by its reviewer after one by the logged-in user
- **THEN** the first thread is `answered` and the second is not

#### Scenario: Comment answered by a Re line
- **WHEN** a later conversation comment by the logged-in user starts with `Re: <url>` for bob's conversation comment, and another names Copilot's review URL only in its second line
- **THEN** bob's comment is `answered` and Copilot's review is not

#### Scenario: A reply older than the comment does not answer it
- **WHEN** the logged-in user's `Re: <url>` comment is older than the comment it names
- **THEN** that comment is not `answered`

#### Scenario: Deleted account
- **WHEN** a thread comment, a review and a conversation comment have no author
- **THEN** each is listed with author `ghost`

#### Scenario: Several pages
- **WHEN** review threads, comments inside a thread, reviews and conversation comments each span two pages
- **THEN** every entry of every page is listed

#### Scenario: Old flag rejected
- **WHEN** `la-fetch-review-comments 7 --all-authors` runs
- **THEN** it exits with the usage-error code

#### Scenario: Logged-in user unreadable
- **WHEN** reading the logged-in user fails
- **THEN** the command fails and writes no JSON file

### Requirement: la-reply-to-pr-thread replies to review bodies and conversation comments
`la-reply-to-pr-thread` SHALL accept, besides a `#discussion_r<ID>` URL and `--comment-id`, a PR review URL
(`https://github.com/<owner>/<repo>/pull/<PR>#pullrequestreview-<ID>`) and a PR conversation-comment URL
(`…#issuecomment-<ID>`). For those it SHALL post a PR conversation comment whose body is `Re: <url>`, a blank line,
then the body read from stdin, and print the new comment's URL. An empty body SHALL still be refused, with no call to
`gh`.

#### Scenario: Reply to a review body
- **WHEN** `la-reply-to-pr-thread https://github.com/o/r/pull/5#pullrequestreview-1` runs with body `Fixed in abc1234.`
- **THEN** it posts to the issue comments of PR 5 a body starting `Re: https://github.com/o/r/pull/5#pullrequestreview-1`, then a blank line and `Fixed in abc1234.`, and prints the new comment's URL

#### Scenario: Reply to a conversation comment
- **WHEN** `la-reply-to-pr-thread https://github.com/o/r/pull/5#issuecomment-9` runs with a body
- **THEN** it posts a conversation comment on PR 5 whose first line is `Re: https://github.com/o/r/pull/5#issuecomment-9`

#### Scenario: Empty body
- **WHEN** a review URL is given with an empty body
- **THEN** the command exits with the usage-error code and calls no `gh`

## MODIFIED Requirements

### Requirement: la-wait-for-reviews settles CodeRabbit only on evidence for the head commit
When CodeRabbit is on the PR, `la-wait-for-reviews` SHALL decide CodeRabbit's outcome for the head commit from
evidence keyed to its SHA, never from a timestamp, and SHALL read that evidence on every poll, from the first one,
alongside the gate. The summary is the CodeRabbit comment whose body carries `summarize by coderabbit.ai`; no other
CodeRabbit comment counts. On each poll:
- **Reviewed** (wins over every other outcome): a CodeRabbit status on the head commit, anywhere in its history,
  whose description contains `Review completed`; or the summary's `final_review_risk_coverage` marker with
  `coveredCommitId` equal to the head SHA; or a CodeRabbit review with `commit_id` equal to the head SHA and a
  non-empty body.
- **Carried forward**: the head commit's latest CodeRabbit status describes `Prior review carried forward`.
- **Rate limited**: the latest CodeRabbit status describes `Review rate limited`.
- **Paused**: the latest CodeRabbit status describes `Review paused`.
- **Skipped**: the latest CodeRabbit status describes a review ending in `review skipped` (e.g. `Incremental review
  skipped`).

Each outcome SHALL be printed as its `coderabbit-settled` item when first seen. Except on a merge conflict, the
command SHALL exit only once the gate has cleared for the head commit, by the outcome of that poll: 0 on reviewed or
carried forward; 3 on rate limited, paused or skipped, with the re-trigger command on stderr for rate limited or
paused. With no outcome it SHALL keep polling until `LA_WAIT_CR_SETTLE` seconds (default 600) after the gate cleared,
then print the `cap` outcome, report on stderr that it proceeds without evidence, and exit 0.

Descriptions SHALL match case-insensitively. Carried forward, rate limited, paused and skipped SHALL be concluded
only from a poll in which every read succeeded; a reviewed outcome stands on any read that succeeded. A failed read
SHALL never end the command. When the PR's head commit changes, the command SHALL print the `head-moved` item and
restart the gate and the settle for the new head commit.

#### Scenario: Placeholder summary does not settle
- **WHEN** `LA_WAIT_CR_SETTLE` is `0`, the summary is newer than the head commit but has no coverage marker, and the head commit has no CodeRabbit status or review
- **THEN** the command prints `coderabbit-settled <sha7> cap`, reports the cap on stderr, never prints a `reviewed` outcome, and exits 0

#### Scenario: Summary covers the head commit
- **WHEN** the summary's coverage marker has `coveredCommitId` equal to the head SHA
- **THEN** the command prints `coderabbit-settled <sha7> reviewed` and exits 0

#### Scenario: Completed status without coverage
- **WHEN** the head commit has a CodeRabbit status `Review completed` and the summary's marker names the previous commit
- **THEN** the command prints `coderabbit-settled <sha7> reviewed` and exits 0

#### Scenario: Review on the head commit
- **WHEN** a CodeRabbit review with a non-empty body has `commit_id` equal to the head SHA
- **THEN** the command prints `coderabbit-settled <sha7> reviewed` and exits 0

#### Scenario: Empty-body review is a thread reply
- **WHEN** `LA_WAIT_CR_SETTLE` is `0` and the only head-commit evidence is a CodeRabbit review with an empty body
- **THEN** the command prints `coderabbit-settled <sha7> cap` and exits 0 without a `reviewed` outcome

#### Scenario: Rate limited
- **WHEN** the head commit's latest CodeRabbit status is `success` with description `Review rate limited`, the summary covers the previous commit and says `Review limit reached`, and a newer CodeRabbit command reply exists
- **THEN** the command prints `coderabbit-settled <sha7> rate-limited`, reports CodeRabbit RATE LIMITED on stderr with the re-trigger command, and exits 3

#### Scenario: Rate limited while checks run
- **WHEN** `LA_WAIT_POLL_SECONDS` is `0`, the head commit's latest CodeRabbit status is `Review rate limited`, and a CheckRun is in progress on the first poll and completed on the second
- **THEN** the command prints `coderabbit-settled <sha7> rate-limited` after the first poll, and exits 3 only after the second

#### Scenario: Rate limited, then reviewed before the checks finish
- **WHEN** `LA_WAIT_POLL_SECONDS` is `0`, a CheckRun is in progress on the first two polls and completed on the third, the head commit's latest CodeRabbit status is `Review rate limited` on the first poll, and `Review completed` from the second
- **THEN** the command prints `coderabbit-settled <sha7> rate-limited` and then `coderabbit-settled <sha7> reviewed`, and exits 0

#### Scenario: Reviewed, then rate limited on the same commit
- **WHEN** the head commit's CodeRabbit statuses are, newest first, `Review rate limited` then `Review completed`
- **THEN** the command prints `coderabbit-settled <sha7> reviewed` and exits 0

#### Scenario: Latest status decides
- **WHEN** the head commit's CodeRabbit statuses are, newest first, `Review paused` then `Review rate limited`
- **THEN** the command prints `coderabbit-settled <sha7> paused`, reports reviews PAUSED on stderr, and exits 3

#### Scenario: Paused
- **WHEN** the head commit's latest CodeRabbit status is `Review paused` and no reviewed evidence exists
- **THEN** the command reports CodeRabbit reviews PAUSED on stderr with the re-trigger command and exits 3

#### Scenario: Skipped
- **WHEN** the head commit's latest CodeRabbit status is `Incremental review skipped` and no reviewed evidence exists
- **THEN** the command prints `coderabbit-settled <sha7> skipped`, reports the skipped review on stderr, and exits 3

#### Scenario: Carried forward
- **WHEN** the head commit's latest CodeRabbit status is `Prior review carried forward`
- **THEN** the command prints `coderabbit-settled <sha7> carried-forward` and exits 0

#### Scenario: Stale rate-limit text with a fresh reply
- **WHEN** `LA_WAIT_CR_SETTLE` is `0`, the summary says `Review limit reached` and covers the previous commit, a newer CodeRabbit reply exists, and the head commit has no CodeRabbit status
- **THEN** the command prints `coderabbit-settled <sha7> cap` and exits 0, not 3

#### Scenario: A failed read is no answer
- **WHEN** `LA_WAIT_CR_SETTLE` is `0` and reading the head commit's statuses fails, with no other evidence
- **THEN** the command prints `coderabbit-settled <sha7> cap` and exits 0

#### Scenario: Head moves during the settle
- **WHEN** the gate clears for one head commit and the PR's head is a different commit at the next poll
- **THEN** the command prints `head-moved <old7> <new7>` and runs the gate again for the new head commit

### Requirement: la-wait-for-reviews prints each new item once
`la-wait-for-reviews` SHALL poll the PR every `LA_WAIT_POLL_SECONDS` seconds (default 60) in one loop and, on each
poll, print to stdout one line per item it has not printed before, and nothing else; progress and diagnostics SHALL
go to stderr. `<sha7>` is the first seven characters of the head commit's SHA; `<login>` is the author's login, or
`ghost` when GitHub gives none. The lines and their keys:

| Line | Item | Key |
|---|---|---|
| `ci-failed <sha7> <url> <name>` | a check in the head commit's rollup, other than a CodeRabbit or Sonar check (by the rules of `la-pr-reviewers`), whose conclusion or state is one of `FAILURE`, `TIMED_OUT`, `CANCELLED`, `ACTION_REQUIRED`, `STARTUP_FAILURE`, `ERROR`; `<url>` is its Details URL, `-` when it has none | a CheckRun or WorkflowRun: SHA and Details URL, else SHA and name; a StatusContext: SHA, context and `startedAt`, else SHA, context and Details URL |
| `review-comment <login> <url>` | a PR review comment (a new thread or a reply) not by the logged-in `gh` user; `<url>` is its `html_url` | the comment id |
| `review <login> <url>` | a PR review with a non-whitespace body not by the logged-in `gh` user; `<url>` is its `html_url` | the review id |
| `pr-comment <login> <url>` | a PR conversation comment not by the logged-in `gh` user, bots included; `<url>` is its `html_url` | the comment id |
| `sonar-done <sha7> <conclusion>` | the head commit has at least one Sonar check suite, every one is `completed`, and no Sonar check in the rollup is non-terminal; `<conclusion>` is the suites' conclusion, the first non-`success` one when they differ | the SHA |
| `coderabbit-settled <sha7> <outcome>` | an outcome of the CodeRabbit settle for the head commit: `reviewed`, `carried-forward`, `rate-limited`, `paused`, `skipped` or `cap` | the SHA and the outcome |
| `head-moved <old7> <new7>` | the head commit differs from the one of this run's previous poll | none: printed on every move |
| `merge-conflict <sha7>` | the PR conflicts with its base (see the merge-conflict requirement) | none: printed on every detection |

Comment items SHALL be read on every poll whether or not CodeRabbit is on the PR, each list once per poll and across
all its pages. Until the logged-in user has been read (retried on every poll), the comment lists SHALL count as
failed reads. An edit to an item already printed SHALL NOT print it again.

The printed keys SHALL persist in the JSON file at `git rev-parse --git-path la/reviews/<owner>/<repo>/<PR>.json`,
so a later run prints only items no run has printed. Each write SHALL re-read the file, take the union with this
run's keys, and replace the file atomically, so keys another run wrote in the meantime survive. A missing file SHALL
count as empty; an unreadable or malformed one SHALL count as empty with a warning on stderr; a failed write SHALL
warn on stderr and the run SHALL continue. Outside a git repository the keys SHALL persist only for the run, with a
note on stderr. A failed read of a source SHALL print none of its items in that poll and SHALL NOT end the command.

#### Scenario: Failed job printed once
- **WHEN** `LA_WAIT_POLL_SECONDS` is `0`, the head commit is `abcdef0123`, the rollup's CheckRun `tests` failed with Details URL `https://github.com/o/r/actions/runs/1/job/2` on the first poll and the rollup is clear by then except for one CheckRun `lint` still in progress on two polls
- **THEN** stdout has `ci-failed abcdef0 https://github.com/o/r/actions/runs/1/job/2 tests` exactly once

#### Scenario: Re-run job is a new item
- **WHEN** the state file already holds the key of the failed `tests` job 2 on the head commit, and the rollup now shows `tests` failed with Details URL `https://github.com/o/r/actions/runs/1/job/5`
- **THEN** stdout has `ci-failed <sha7> https://github.com/o/r/actions/runs/1/job/5 tests` and no line for job 2

#### Scenario: Same-named checks are distinct items
- **WHEN** two failed CheckRuns are both named `tests`, with Details URLs ending `job/2` and `job/4`
- **THEN** stdout has one `ci-failed` line for each

#### Scenario: Re-reported external status is a new item
- **WHEN** the state file holds the key of a failed StatusContext `ext-ci` with Details URL `https://ci.example/1` and `startedAt` `2026-01-01T00:00:00Z`, and the rollup now shows it failed with the same URL and `startedAt` `2026-01-02T00:00:00Z`
- **THEN** stdout has `ci-failed <sha7> https://ci.example/1 ext-ci`

#### Scenario: Review bots are not CI
- **WHEN** the rollup has a failed CodeRabbit StatusContext and a failed `SonarCloud Code Analysis` CheckRun and no other failed check
- **THEN** stdout has no `ci-failed` line

#### Scenario: CodeRabbit comments and reviews
- **WHEN** CodeRabbit is on the PR, has review comments 11 (a thread) and 12 (a reply), a review 21 with a body, and a review 22 with an empty body
- **THEN** stdout has `review-comment coderabbitai[bot] <url>` for each of 11 and 12, `review coderabbitai[bot] <url>` for 21, and nothing for 22

#### Scenario: Comments from every author
- **WHEN** the logged-in user is `me`, `alice` has review comment 13 and a review 23 with a body, `bob` and `sonarqubecloud[bot]` have conversation comments 31 and 32, and `me` has review comment 14 and conversation comment 33
- **THEN** stdout has `review-comment alice <url>` for 13, `review alice <url>` for 23, `pr-comment bob <url>` for 31 and `pr-comment sonarqubecloud[bot] <url>` for 32, and nothing for 14 or 33

#### Scenario: Comments without CodeRabbit
- **WHEN** CodeRabbit is not on the PR and `alice` has a review comment
- **THEN** stdout has its `review-comment alice <url>` line

#### Scenario: Deleted account
- **WHEN** a review comment has no author
- **THEN** its line reads `review-comment ghost <url>`

#### Scenario: Logged-in user not yet read
- **WHEN** `LA_WAIT_POLL_SECONDS` is `0`, reading the logged-in user fails on the first poll and succeeds on the second, a CheckRun is in progress on the first poll, and `alice` has a review comment
- **THEN** the first poll prints no comment line and the second prints `review-comment alice <url>` once

#### Scenario: Each comment list read once per poll
- **WHEN** CodeRabbit has no status on the head commit, so its presence is decided from the conversation comments
- **THEN** each poll requests the review comments, reviews and conversation comments once each

#### Scenario: Edited comment is not printed again
- **WHEN** the state file holds the key of review comment 11 and comment 11 now has a later `updated_at`
- **THEN** stdout has no line for comment 11

#### Scenario: Sonar done
- **WHEN** the head commit's only Sonar check suite is `completed` with conclusion `failure` and the rollup's Sonar check is `COMPLETED`
- **THEN** stdout has `sonar-done <sha7> failure` once

#### Scenario: Sonar suite still queued
- **WHEN** the head commit's Sonar check suite is `queued`
- **THEN** stdout has no `sonar-done` line

#### Scenario: A second run prints nothing new
- **WHEN** a run printed items for the head commit and exited, and a second run sees the same mergeable PR state with the same state file
- **THEN** the second run prints no item lines and exits with the same code

#### Scenario: Keys of a concurrent run survive
- **WHEN** another run adds a key to the state file while this run is polling, and this run then writes its own keys
- **THEN** the file holds both runs' keys

#### Scenario: Malformed state file
- **WHEN** the state file holds `not json` and the rollup has a failed check
- **THEN** stderr warns about the state file, stdout prints the `ci-failed` line, and the command proceeds as with an empty file

#### Scenario: Outside a git repository
- **WHEN** the command runs with `--repo o/r` in a directory that is not a git repository and the rollup has a failed check
- **THEN** stderr notes the keys are not persisted, and stdout prints the `ci-failed` line

#### Scenario: Progress on stderr
- **WHEN** a poll finds checks still pending
- **THEN** the progress message is on stderr and stdout has no line for it
