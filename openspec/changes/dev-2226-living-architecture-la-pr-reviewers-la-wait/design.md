## Context

`shared/scripts/review-bots.bash` holds the bot detection both `pr-reviewers.sh` and `wait-for-reviews.sh` source.
Sonar is detected only from a rollup check; Stage 0b of `wait-for-reviews.sh` settles on any CodeRabbit comment's
`updated_at` beating HEAD's committer date and greps the newest CodeRabbit comment for rate-limit text. Comments are
read without `--paginate` (first 30 only). Any failed read in Stage 0b kills the script under `set -e`. Both twins
run the same bundled scripts; the corpus pins them with neutral `shim-*` cases through a fake `gh` (first route whose
tokens all appear in argv wins, `--jq` applied with real jq). The fake exists twice (`python/tests/conftest.py`,
`python/tests/test_conformance.py`). Host `gh` is 2.45 (no `--slurp`).

Probe results (MotleyAI/slayer and MotleyAI/living-architecture, ~60 PRs, 2026-11-09):

- CodeRabbit posts per-commit statuses (`repos/R/commits/<sha>/statuses`, newest first) with descriptions
  `Review in progress` (pending), `Review completed`, `Review rate limited`, `Review paused`,
  `Prior review carried forward` (all `success` but the first). The rollup's StatusContext has no `description`.
- Every HEAD with a real review: review submitted → summary marker updated ~4 s later → `Review completed` ~7 s
  later (e.g. slayer#563 `2f37591e`: 11:50:57 / 11:51:01 / 11:51:04).
- CodeRabbit thread replies create empty-body review objects with `commit_id` = HEAD, also on rate-limited and
  paused HEADs (slayer#552 `f2f565e4`, #547 `f952a1de`). Real reviews have a body starting
  `<!-- coderabbit-ai-generated:v1 -->`.
- The marker `<!-- final_review_risk_coverage:{"sourceCommitId":…,"coveredCommitId":…,"kind":"reviewed"} -->` is
  not updated for every HEAD: a clean `Review completed` (living-architecture#19 `d11c796f`) and
  `Prior review carried forward` (slayer#557 `58bca836`) leave it on the previous SHA. A rate-limited HEAD leaves
  it, and the rate-limit text, on the previous SHA (slayer#560 `5c84de18`).
- One HEAD can get `Review completed` and later, on a re-trigger, `Review rate limited` (slayer#547 `29b8a4c4`).
- Check suites: idle apps sit `queued` with 0 runs forever; `sonarqubecloud` suites in the org always completed
  2–3 min after the push. No suite carries a Sonar project key.

## Goals / Non-Goals

**Goals:**
- Every presence and readiness decision is keyed to HEAD's SHA; no timestamp decides anything.
- One definition of "Sonar on HEAD" and of the HEAD snapshot in `review-bots.bash`, used by both scripts.
- A wait never answers for a SHA other than the one it gated; a failed read never ends it or answers it.

**Non-Goals:**
- Detecting CodeRabbit presence earlier than its first status or comment.
- A suite-based Sonar project key (suites carry none).
- Modelling multi-page responses in the fake `gh` (selection runs once, locally, over streamed items).
- Any release or version bump.

## Decisions

1. **CodeRabbit outcome from all three HEAD-keyed sources, reading the status `description`** (user). Reviewed:
   any `Review completed` status on HEAD, summary marker `coveredCommitId == HEAD`, or a non-empty CodeRabbit
   review on HEAD; reviewed wins. Latest status `Prior review carried forward` → 0, `Review rate limited` /
   `Review paused` → 3; else poll to the cap. Weighed against the brief as amended by its correction comment
   (status dropped; marker on another SHA + rate-limit text → 3): that gives a false exit 3 right after a push that
   follows a rate-limited HEAD, counts thread-reply reviews, and waits the full cap on clean, carried-forward and
   paused HEADs. The description is what tells the outcomes apart, so the comment's reason for dropping the status
   does not apply to it.
2. **Rate limit from HEAD's status only; the summary-text grep goes** (default): the text persists from an earlier
   HEAD.
3. **Paused exits 3** (default): no review will run without a trigger, and `process-reviews` treats exit 3 and the
   cap alike. `shared/cli.yaml` exit 3 becomes `3: CodeRabbit rate limited or paused`.
4. **Carried forward exits 0** (default): CodeRabbit decided nothing new needs review; the existing threads stand.
5. **DEV-2084 folded in** (default): the summary is selected by `summarize by coderabbit.ai`; `LA_WAIT_CR_SETTLE`
   (seconds, default 600) sets the cap. The user approved marking DEV-2084 a Duplicate of DEV-2226 after merge (user).
6. **Description match**: case-insensitive substring of `review completed`, `carried forward`, `rate limited`,
   `paused` (default). An unknown description falls through to the cap.
7. **No suite-based Sonar key** (default): suites carry no key. The existing chain runs whenever Sonar is present,
   so a suite-only presence still returns the config or properties key (slayer#560 gave `null` only because the
   chain was skipped).
8. **`la-pr-reviewers` reads suites only when the rollup has no Sonar check** (default): presence is settled by the
   check; saves two API calls.
9. **Stage 0a always reads HEAD's Sonar suites** (codex): a re-requested suite can be `queued` while the rollup still
   holds the completed run of the same SHA. Any non-`completed` Sonar suite is pending, listed `<slug> (check suite)`.
10. **Idle Sonar install risk accepted** (default): a Sonar app that never analyses keeps its suite `queued`, so the
    gate times out naming it. None in the org today; failing closed is the safer error.
11. **One HEAD snapshot per poll; restart on a moved HEAD** (codex): each poll reads
    `gh pr view --json headRefOid,statusCheckRollup` once and keys suites, statuses and reviews to that SHA. Stage 0a
    records the SHA it cleared; when Stage 0b reads a different head it prints
    `Stage 0b: HEAD moved from <a> to <b> — restarting Stage 0a.` and re-enters Stage 0a with fresh timers. Every
    existing rollup route in the wait and pr-reviewers fixtures changes its match token.
12. **Paginated list reads, selected once locally** (codex): comments, statuses, reviews and check suites are read
    with `gh api --paginate --jq '.[]'` (`'.check_suites[]'` for suites) and selected with one local `jq -s`, so
    per-page jq can never pick a per-page winner. Multi-page fake modelling rejected (codex): with a per-page filter
    of `.[]` a page boundary cannot change the result.
13. **Status order** (codex): "latest" is the first CodeRabbit status in API order (newest first); `Review completed`
    is searched across the full history separately.
14. **Failed reads** (default, refined by codex): every fallible read is wrapped explicitly (no `set -e` exits, no
    jq crash on malformed JSON). Reviewed evidence from any successful read settles; carried forward, rate limited
    and paused need every read of the poll to have succeeded; otherwise the poll is unknown and polling continues.
    The initial CodeRabbit-presence read in Stage 0b is retried the same way.
15. **HEAD re-read every poll** (default).
16. **One fake `gh` module with sequenced responses** (codex): the unit-test and conformance fakes merge into one
    module; a route may list `responses` (each `stdout`/`exit`) served in call order, the last repeating. The case
    format in `conformance/README.md` documents it.
17. **Case rename** (default): `shim-wait-for-reviews-fresh-summary` → `shim-wait-for-reviews-summary-covers-head`.
18. **Script messages** (user; `<h>` = HEAD's first 7 characters, `<PR>`/`<R>` the PR and repo):
    - stdout `Stage 0b: CodeRabbit reviewed HEAD <h> (<evidence>).`, evidence one of `status "Review completed"`,
      `summary covers HEAD`, `review on HEAD` (first found, in that order)
    - stdout `Stage 0b: CodeRabbit carried its prior review forward to HEAD <h>.`
    - stderr `Stage 0b: CodeRabbit is RATE LIMITED — no review ran for HEAD <h>.`
    - stderr `Stage 0b: CodeRabbit reviews are PAUSED — no review ran for HEAD <h>.`
    - each of the two followed by stderr
      `Stage 0b: re-trigger with 'gh pr comment <PR> --repo <R> --body "@coderabbitai review"' once the window clears.`
    - stdout `Stage 0b: waiting for CodeRabbit on HEAD <h> (elapsed <N>m). Sleeping 30s.`
    - stderr `Stage 0b: hit <N>m cap without CodeRabbit evidence for HEAD <h> — proceeding anyway.`
    - Stage 0a pending entry for a suite: `<slug> (check suite)`.
19. **`process-reviews` SKILL.md wording** (user, approved wording), applied verbatim:
    - "Sources on this PR", after "…detected from the PR itself, never from the repo config.": "Sonar counts as
      present once HEAD has a Sonar check suite, before its check run exists."
    - The Stage 0a+0b intro: "Run `la-wait-for-reviews` — it bundles the status-check rollup gate (Stage 0a) AND
      the CodeRabbit settle on HEAD (Stage 0b) into a single invocation. No inline bash."
    - Exit paragraph: "The script exits 0 when both stages clear (or when CodeRabbit is not on the PR, detected the
      same way as `la-pr-reviewers`), 1 if the status-check gate doesn't clear within 30 minutes, and 3 when
      CodeRabbit is rate limited or paused on HEAD. Stage 0b is best-effort with a 10-minute cap: on the cap the
      script reports "proceeding anyway" and still exits 0; see the "CodeRabbit did not review this HEAD" rule
      below."
    - Non-terminal list, new bullet: "a Sonar check suite on HEAD that is not `completed` — SonarQube Cloud
      creates its check run only when the analysis finishes."
    - Replacing the block from "Why the CodeRabbit settle is needed…" through the "Summary `updated_at`" bullet:
      "Why Stage 0b is keyed to HEAD's SHA: CodeRabbit refreshes its summary as a placeholder seconds after a push,
      and its status reaches the rollup only when it finishes, so neither the rollup nor a timestamp shows whether
      HEAD was reviewed. Stage 0b reads only evidence tied to HEAD's SHA. The summary is the comment carrying the
      `summarize by coderabbit.ai` marker; command replies never count.
      - **Reviewed** (exit 0): a CodeRabbit status on HEAD described `Review completed`, the summary's
        `final_review_risk_coverage` marker naming HEAD as `coveredCommitId`, or a CodeRabbit review on HEAD with a
        body (empty-body reviews are thread replies). Reviewed wins over every other outcome.
      - **Carried forward** (exit 0): HEAD's latest CodeRabbit status is `Prior review carried forward`; the
        existing threads stand for HEAD.
      - **Rate limited or paused** (exit 3): HEAD's latest CodeRabbit status is `Review rate limited` or
        `Review paused`. The summary's rate-limit text is not used: it stays from an earlier HEAD until CodeRabbit
        reaches the new one.
      - Anything else: keep polling until the cap."
    - The rule heading: "**CodeRabbit did not review this HEAD (rate limited or paused, script exit 3, or the
      10-minute settle cap).**"

Architecture: system principle 1 (one behaviour in both twins, the corpus decides) and principle 2 (texts, exit
labels and command surfaces only from `shared/`) apply; the scripts and `cli.yaml` live in `shared/`. No arc42
contradiction. The spec delta attaches to `review-detection` on the `review` node.

## Risks / Trade-offs

- CodeRabbit's description strings are not a documented API. An unknown or reworded one falls through to the cap
  (safe, slower); a reworded `Review completed` still settles through the marker or a real review.
- An installed but idle Sonar app blocks Stage 0a until its timeout (decision 10).
- Restarting Stage 0a on every moved HEAD can extend the wait while pushes keep landing; each restart is reported.
- More API calls per poll (snapshot, suites, comments, statuses, reviews), all paginated.
