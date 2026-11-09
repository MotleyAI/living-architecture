## 1. Test harness (pr-tests stage)

- [x] 1.1 Merge the two fake `gh` copies (`python/tests/conftest.py` `FAKE_GH`, `python/tests/test_conformance.py`
  `FAKE_GH`) into one test module both import. Add sequenced responses: a route may carry `responses` (a list of
  `{stdout, exit}`) served in call order per route, the last repeating; call counts live in a file under the case's
  own temp dir. `FakeGh.route` accepts the same; the conformance case loader passes `responses` through. Document
  the `responses` key in `conformance/README.md`'s case format. Every existing test and case still passes.

## 2. Tests (pr-tests stage; failing until implemented)

Fixture conventions for everything below: HEAD is `abc` (full SHA in fixtures where a marker needs one: use `abc`
literally, it is compared as a string); the snapshot route matches `pr view headRefOid,statusCheckRollup`; list
endpoints are read with `--paginate --jq '.[]'` (suites `'.check_suites[]'`), so fixtures give the plain JSON
array/object. The summary body carries `<!-- This is an auto-generated comment: summarize by coderabbit.ai -->`
and, where it covers a commit, `<!-- final_review_risk_coverage:{"sourceCommitId":"<sha>","coveredCommitId":"<sha>","kind":"reviewed"} -->`.

- [x] 2.1 Align existing fixtures (approved by the plan, decision 11): every wait/pr-reviewers rollup route matches
  the snapshot call; the wait cases and `_cr_routes` drop the committer-date route and gain suites/statuses/reviews
  routes; summary bodies gain the summarize marker. Rename `shim-wait-for-reviews-fresh-summary` →
  `shim-wait-for-reviews-summary-covers-head` (its summary covers `abc`; new stdout golden). No other assertion or
  exit code changes except the `fresh-summary` / rate-limited stdout/stderr texts the plan's messages replace.
- [x] 2.2 `python/tests/test_review_scripts.py` + neutral case, pr-reviewers: `shim-pr-reviewers-sonar-suite-only` —
  rollup without Sonar, `sonarqubecloud` suite `queued`, config key `cfg_key` → `{"present": true, "project_key": "cfg_key"}`.
  Also a pr-reviewers test where the suites read fails → exit 2, no JSON.
- [x] 2.3 Stage 0a (with `LA_WAIT_GATE_TIMEOUT=0`, `LA_WAIT_POLL_SECONDS=0` where it must time out):
  `shim-wait-for-reviews-sonar-suite-queued` (exit 1, stdout lists `sonarqubecloud (check suite)`, no "gate clear");
  `shim-wait-for-reviews-sonar-suite-beside-completed-check` (completed Sonar run + queued suite → exit 1);
  completed suite clears (Python test); `shim-wait-for-reviews-suite-read-fails` (exit 1, never "gate clear").
- [x] 2.4 Stage 0b cases, each a Python test and a neutral case:
  `shim-wait-for-reviews-placeholder-summary` (`LA_WAIT_CR_SETTLE=0`, summary newer than the commit without a
  coverage marker → cap on stderr, exit 0, no "reviewed");
  `shim-wait-for-reviews-status-completed` (status `Review completed`, marker on a previous SHA → exit 0);
  `shim-wait-for-reviews-review-on-head` (non-empty CodeRabbit review on `abc` → exit 0);
  `shim-wait-for-reviews-empty-review-ignored` (`LA_WAIT_CR_SETTLE=0`, only an empty-body review on `abc` → cap);
  `shim-wait-for-reviews-rate-limited` (updated: latest status `success`/`Review rate limited`, summary covering a
  previous SHA with `Review limit reached`, a newer CodeRabbit command reply → exit 3, RATE LIMITED + re-trigger);
  `shim-wait-for-reviews-reviewed-then-rate-limited` (statuses newest first: rate limited, completed → exit 0);
  `shim-wait-for-reviews-latest-status-decides` (newest first: paused, rate limited → PAUSED, exit 3);
  `shim-wait-for-reviews-paused` (exit 3, PAUSED + re-trigger);
  `shim-wait-for-reviews-carried-forward` (exit 0, carried-forward message);
  `shim-wait-for-reviews-stale-summary-fresh-reply` (`LA_WAIT_CR_SETTLE=0`, summary with rate-limit text covering
  a previous SHA, a newer reply, no status on `abc` → cap, exit 0, not 3);
  `shim-wait-for-reviews-statuses-read-fails` (`LA_WAIT_CR_SETTLE=0`, statuses read fails, no other evidence → cap).
- [x] 2.5 Python only: parametrized failure test — each Stage 0b read (snapshot, comments, statuses, reviews,
  suites) failing, and one returning invalid JSON, with `LA_WAIT_CR_SETTLE=0`: the script never crashes, never
  exits 3, never reports reviewed off the failed source; with a covering summary and a failing statuses read it
  still settles as reviewed (summary covers HEAD).
- [x] 2.6 HEAD moves (sequenced responses): snapshot returns `abc` for Stage 0a then `def` in Stage 0b → stdout
  `Stage 0b: HEAD moved from abc to def — restarting Stage 0a.`, then Stage 0a and 0b run for `def` (evidence for
  `abc` must not settle; evidence for `def` settles). One Python test and neutral case
  `shim-wait-for-reviews-head-moves`.
- [x] 2.7 `shim-wait-for-reviews-coderabbit-by-comment`: summary covers `abc` → "reviewed HEAD abc (summary covers
  HEAD)".
- [x] 2.8 List every new or renamed case in `conformance/INVENTORY.md` beside the wait-for-reviews / pr-reviewers
  rows. New goldens hand-written (`golden: manual`), reason in the commit message. Verify each new test/case fails
  against the current scripts (`shim-wait-for-reviews-suite-read-fails` exits 1 there too; its Python test fails).
- [x] 2.9 Codex review of the tests against this change (pr-tests Step 2); resolve findings with the user.

## 3. shared/ (pr-implement stage)

- [x] 3.1 `review-bots.bash`: snapshot helper (`gh pr view --json headRefOid,statusCheckRollup`), Sonar suites of a
  SHA (`--paginate --jq '.check_suites[]'`, slug match local), shared paginated-list read; keep `rb_coderabbit`
  semantics. Header comment updated.
- [x] 3.2 `pr-reviewers.sh`: Sonar presence by check or suite (suites read only without a rollup Sonar check); key
  chain unchanged; suite read failure → exit 2.
- [x] 3.3 `wait-for-reviews.sh`: Stage 0a from the snapshot + always the Sonar suites, failed read = unknown; record
  the cleared SHA. Stage 0b per design.md decisions 1–6, 11–15, messages per decision 18, `LA_WAIT_CR_SETTLE`;
  remove the committer-date threshold and the text grep. Header comment rewritten (stages, evidence, env knobs
  `LA_WAIT_GATE_TIMEOUT` / `LA_WAIT_POLL_SECONDS` / `LA_WAIT_CR_SETTLE`, exits 0/1/2/3/64).
- [x] 3.4 `shared/cli.yaml`: `la-wait-for-reviews` exit `3: CodeRabbit rate limited or paused`.
- [x] 3.5 `scripts/sync-shared`; `scripts/sync-shared --check` passes, both snapshots' `CONTRACT_HASH` agree.

## 4. Docs

- [x] 4.1 `plugin/skills/process-reviews/SKILL.md`: apply design.md decision 19 verbatim.
- [x] 4.2 Check `plugin/skills/pr-review/SKILL.md`, `docs/commands.md` and `README.md` for wording implying a
  timestamp settle or any-comment summary; align (`rg -n -i "updated_at|committedDate|summary comment"`).

## 5. Verify

- [x] 5.1 Python: `uv run pytest -q`, `uv run ruff check src tests`, `uv run basedpyright src tests` green.
- [x] 5.2 npm: `npm run lint && npm run typecheck`, `npm test`, `npm run build && npm run conformance` green.
- [x] 5.3 `scripts/conformance-cross` green; `la-arch-check` green; `shellcheck` clean on the three scripts.

## 6. After merge

- [x] 6.1 Mark DEV-2084 as a Duplicate of DEV-2226 in Linear (user approved in pr-plan, 2026-11-09).
