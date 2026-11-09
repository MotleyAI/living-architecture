## Why

Right after a push, `la-pr-reviewers` reports Sonar absent and `la-wait-for-reviews` reports CodeRabbit settled
before either bot has delivered anything for HEAD, so `/la:process-reviews` sweeps an empty view and calls the PR
clean (DEV-2226, observed on MotleyAI/slayer#560). Both races have one cause: readiness is inferred from signals
not keyed to HEAD's SHA — the existence of a Sonar check run (SonarQube Cloud creates it only when its analysis
finishes) and a CodeRabbit comment timestamp compared with the commit date (CodeRabbit refreshes its summary as a
placeholder seconds after the push). The same Stage 0b code also reads the newest CodeRabbit comment of any kind as
the summary, so a command reply hides a rate limit (DEV-2084, folded in here).

## What Changes

- Sonar presence (`la-pr-reviewers`) also comes from HEAD's check suites: a suite whose app slug contains `sonar`
  counts, so Sonar is present from the push on. The project-key chain is unchanged.
- `la-wait-for-reviews` Stage 0a treats any Sonar check suite on HEAD that is not `completed` as pending, whatever
  the rollup shows.
- Stage 0b settles CodeRabbit only on evidence keyed to HEAD's SHA: a `Review completed` status on HEAD, the
  summary's coverage marker naming HEAD, or a non-empty CodeRabbit review on HEAD. HEAD's latest CodeRabbit status
  `Prior review carried forward` settles; `Review rate limited` or `Review paused` exits 3. The commit-date
  threshold and the summary-text rate-limit check are removed.
- The summary is the CodeRabbit comment carrying `summarize by coderabbit.ai`; other CodeRabbit comments never
  count. `LA_WAIT_CR_SETTLE` (seconds, default 600) sets the Stage 0b cap.
- Every poll reads one HEAD snapshot (HEAD and rollup together) and keys every other read to it; when HEAD moves
  during Stage 0b, the wait restarts at Stage 0a. List reads are paginated and selected once, locally. A failed read
  is never a terminal answer.
- Exit 3 of `la-wait-for-reviews` means "CodeRabbit rate limited or paused" (was "rate limited").
- The test `gh` fake (one shared module for the unit tests and the conformance runner) serves sequenced responses.
- `plugin/skills/process-reviews/SKILL.md` describes the HEAD-keyed settle and the Sonar suite.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `review-detection`: Sonar presence includes a Sonar check suite on HEAD; `la-wait-for-reviews` waits for a
  pending Sonar suite and settles CodeRabbit only on evidence for HEAD's SHA.

## Impact

- `shared/scripts/review-bots.bash`, `shared/scripts/pr-reviewers.sh`, `shared/scripts/wait-for-reviews.sh`,
  `shared/cli.yaml` (exit 3 label); both twins' vendored snapshots via `scripts/sync-shared`.
- `python/tests/test_review_scripts.py`, `python/tests/conftest.py`, `python/tests/test_conformance.py` (shared
  fake `gh` with sequenced responses), `conformance/README.md` (case format), `conformance/cases/shim-wait-for-reviews-*`,
  `conformance/cases/shim-pr-reviewers-*`, `conformance/INVENTORY.md`.
- `plugin/skills/process-reviews/SKILL.md`.
- No release or version bump.
