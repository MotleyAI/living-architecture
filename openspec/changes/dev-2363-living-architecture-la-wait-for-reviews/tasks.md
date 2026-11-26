## 1. Tests first (pr-tests)

- [x] 1.1 Re-route every snapshot route from the `headRefOid,statusCheckRollup` token to `headRefOid,mergeable,statusCheckRollup` in `conformance/la/cases/shim-wait-for-reviews-*` and `shim-pr-reviewers-*`, and in `python/la/tests/test_review_scripts.py`; verify by the cases failing until the script changes
- [x] 1.2 Merge-conflict conformance cases (neutral, `golden: manual`) for every scenario of "la-wait-for-reviews stops on a merge conflict", listed in `conformance/la/INVENTORY.md`, plus Python tests for conflicting → item + exit 4 and unknown → keeps polling; verify they fail on the current script
- [x] 1.3 Every wait-for-reviews case and test: a `user` route, comment routes read regardless of CodeRabbit, and the new author-tagged item lines in place of `coderabbit-comment` / `coderabbit-review`; new cases for the "prints each new item once" scenarios (every author, without CodeRabbit, `ghost`, logged-in user not yet read, one read per list per poll, multi-page lists); verify they fail
- [x] 1.4 Rename `shim-fetch-coderabbit-threads-*` to `shim-fetch-review-comments-*` with command `la-fetch-review-comments`; replace `-all-authors` with a case rejecting `--all-authors`; add cases for every scenario of "la-fetch-review-comments lists every reviewer's comments"; rename and adapt `test_coderabbit_threads_*`; INVENTORY rows; verify they fail
- [x] 1.5 Reply cases: replace `shim-reply-to-pr-thread-review-summary-url` and `test_reply_rejects_review_summary_url` with the review-body and conversation-comment reply scenarios plus the empty-body refusal; verify they fail
- [x] 1.6 Command-name lists: `test_format.py`, `test_contract.py`, `test_contract_split.py`, `test_cli_entry_modules.py`, `test_shims.py` (in `python/la/tests/`), and `node/la/test/format.test.ts` name `la-fetch-review-comments` and `fetch-review-comments.sh`; verify they fail

## 2. Merge conflict (watcher)

- [x] 2.1 `rb_snapshot` reads and projects `mergeable`; verify `shim-pr-reviewers-*` stay green
- [x] 2.2 `wait-for-reviews.sh`: after `head-moved`, on `CONFLICTING` print only `merge-conflict <sha7>`, report on stderr, exit 4 before other reads, items, state writes and the timeout check; header lists the item and exit; `shared/la/cli.yaml` exit map gains `4`; verify the 1.2 cases pass

## 3. Comment items for every author (watcher)

- [x] 3.1 Read the logged-in user (retried each poll; while unknown the comment lists are failed reads); read review comments, reviews and conversation comments once per poll whatever CodeRabbit's presence; `rb_coderabbit` takes the poll's conversation comments (`la-pr-reviewers` unchanged); CodeRabbit settle evidence from the same lists; verify the call-count case passes
- [x] 3.2 Emit `review-comment` / `review` / `pr-comment <login> <url>` (null author → `ghost`, self excluded, empty-body reviews skipped) keyed by kind + id; verify the 1.3 cases pass

## 4. la-fetch-review-comments

- [x] 4.1 Rename the script to `shared/la/scripts/fetch-review-comments.sh`, the `shared/la/cli.yaml` entry (help text), the Python entry module and `python/la/pyproject.toml` script, the `node/la/package.json` bin (and `node/package-lock.json`); drop `--all-authors`; verify the 1.6 lists pass
- [x] 4.2 Self, `ghost`, `threads` / `reviews` / `comments` with `answered` (thread: last comment is self; review / conversation comment: a later self conversation comment whose first line is `Re: <url>`), all pages, Markdown sections and JSON at `${TMPDIR:-/tmp}/review-comments-<pr>-<ts>.json`; verify the 1.4 cases pass

## 5. la-reply-to-pr-thread

- [x] 5.1 Accept `#pullrequestreview-<ID>` and `#issuecomment-<ID>` URLs: post `Re: <url>`, a blank line and the body to the PR's issue comments and print the URL; usage text names the forms; verify the 1.5 cases pass

## 6. Skills and docs (approved wording in design.md, verbatim)

- [x] 6.1 process-reviews and pr-review: the merge-conflict wording and the every-reviewer wording (a–k, and the pr-review reply-drafts sentence); verify the skill tests (`test_skills.py`) pass
- [x] 6.2 Rename `plugin/la/skills/fetch-coderabbit-threads/` to `fetch-review-comments/` with the approved text; reply-to-pr-thread edits a–c; `docs/commands.md` and `docs/skills.md` rows; verify `test_skills.py` and `plugin validate plugin/la` pass

## 7. Sync and gates

- [x] 7.1 `scripts/sync-shared`, then verify `scripts/sync-shared --check` and the drift tests pass
- [x] 7.2 Run the local test scope (the affected Python tests and the `conformance/la` cases through both twins), `ruff`, `basedpyright`, npm lint/typecheck, `la-arch-check` and `openspec validate dev-2363-living-architecture-la-wait-for-reviews --strict`; verify all green
- [x] 7.3 Drop the stale `fetch-coderabbit-threads` entries from `python/{la,dr}/tests/durations/*.json`; verify no test names the old command

## 8. Sonar pre-check (skills)

- [ ] 8.1 pr-review and pr-implement: the Sonar pre-check wording (design.md), verbatim; verify `test_skills.py` and `plugin validate plugin/la` pass
