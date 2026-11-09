#!/usr/bin/env bash
# Wait for a PR's reviews + CI to be ready for the process-reviews triage.
#
#   Stage 0a — gate: poll HEAD's snapshot (SHA + status-check rollup) and HEAD's Sonar check suites until no check
#     is PENDING / EXPECTED / QUEUED / IN_PROGRESS / WAITING / REQUESTED and every Sonar suite is `completed`
#     (SonarQube Cloud creates its check run only when the analysis finishes). A failed read keeps the gate pending.
#   Stage 0b — CodeRabbit settle, when CodeRabbit is on the PR (as la-pr-reviewers detects it). Only evidence keyed
#     to the SHA Stage 0a cleared counts. Reviewed (wins): a CodeRabbit status on HEAD described "Review completed",
#     the summary comment's (`summarize by coderabbit.ai`) coverage marker naming HEAD, or a CodeRabbit review on
#     HEAD with a body. Otherwise, from a poll whose reads all succeeded, HEAD's latest CodeRabbit status: "Prior
#     review carried forward" settles, "Review rate limited" / "Review paused" exit 3. A moved HEAD restarts
#     Stage 0a. Best-effort: at the cap it proceeds anyway.
#
# Env: LA_WAIT_GATE_TIMEOUT (Stage 0a cap, seconds, default 1800), LA_WAIT_POLL_SECONDS (Stage 0a poll, default 60),
#      LA_WAIT_CR_SETTLE (Stage 0b cap, seconds, default 600).
#
# Exits 0 when both stages clear (or CodeRabbit is not on the PR, or the Stage 0b cap is hit), 1 on the Stage 0a
# timeout, 2 when the repo can't be resolved, 3 when CodeRabbit is rate limited or paused on HEAD, 64 on usage.
#
# Usage:
#   la-wait-for-reviews <PR_NUMBER> [--repo OWNER/REPO]
#
# Defaults the repo to the current git working directory via ``gh repo view``.

set -euo pipefail

# shellcheck source=review-bots.bash
source "$(dirname "${BASH_SOURCE[0]}")/review-bots.bash"

usage() {
    cat >&2 <<EOF
usage: la-wait-for-reviews <PR_NUMBER> [--repo OWNER/REPO]

  <PR_NUMBER>           required, the PR number
  --repo OWNER/REPO     optional, defaults to the repo of the current git directory
EOF
    exit 64
}

PR=""
REPO=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --repo)
            REPO="$2"
            shift 2
            ;;
        -h|--help)
            usage
            ;;
        --*)
            echo "unknown flag: $1" >&2
            usage
            ;;
        *)
            if [[ -z "$PR" ]]; then
                PR="$1"
                shift
            else
                echo "extra positional arg: $1" >&2
                usage
            fi
            ;;
    esac
done

if [[ -z "$PR" ]]; then
    usage
fi

if [[ -z "$REPO" ]]; then
    REPO=$(gh repo view --json nameWithOwner --jq '.nameWithOwner' 2>/dev/null \
        || { echo "could not resolve --repo from gh repo view" >&2; exit 2; })
fi

GATE_TIMEOUT=${LA_WAIT_GATE_TIMEOUT:-1800}
POLL=${LA_WAIT_POLL_SECONDS:-60}
CR_SETTLE=${LA_WAIT_CR_SETTLE:-600}
CR_POLL=30

# HEAD's snapshot into HEAD_SHA and ROLLUP, then its Sonar suites into SUITES. Returns 1 when the snapshot read
# fails, 2 when the suites read does.
read_head() {
    local snapshot
    snapshot=$(rb_snapshot "$PR" "$REPO" 2>/dev/null) || return 1
    HEAD_SHA=$(jq -r '.headRefOid' <<<"$snapshot")
    ROLLUP=$(jq -c '.statusCheckRollup' <<<"$snapshot")
    SUITES=$(rb_sonar_suites "$HEAD_SHA" "$REPO" 2>/dev/null) || return 2
}

# ---------------------------------------------------------------------------
# Stage 0a — gate (cap LA_WAIT_GATE_TIMEOUT); leaves HEAD_SHA and ROLLUP at the snapshot it cleared
# ---------------------------------------------------------------------------

gate() {
    local start elapsed pending rc=0
    start=$(date +%s)
    while :; do
        rc=0
        read_head || rc=$?
        if (( rc == 1 )); then
            pending="(unknown — could not read the check rollup)"
        else
            pending=$(jq -r '[.[]
                | select(
                    (.__typename == "StatusContext"
                       and (.state == "PENDING" or .state == "EXPECTED"))
                    or ((.__typename == "CheckRun" or .__typename == "WorkflowRun")
                       and (.status == "QUEUED" or .status == "IN_PROGRESS"
                         or .status == "WAITING" or .status == "REQUESTED"
                         or .status == "PENDING"))
                  )
                | (.name // .context)] | join(", ")' <<<"$ROLLUP")
            if (( rc == 2 )); then
                pending="${pending:+$pending, }(unknown — could not read the check suites)"
            else
                pending=$(jq -r --arg rollup "$pending" '[($rollup | select(. != "")),
                    (.[] | select((.status // "" | ascii_downcase) != "completed") | "\(.app.slug) (check suite)")]
                    | join(", ")' <<<"$SUITES")
            fi
            if [[ -z "$pending" ]]; then
                echo "Stage 0a: gate clear."
                return
            fi
        fi

        elapsed=$(( $(date +%s) - start ))
        echo "Stage 0a: pending — $pending (elapsed $((elapsed / 60))m). Sleeping ${POLL}s."

        if (( elapsed >= GATE_TIMEOUT )); then
            echo "Stage 0a: gate timed out after $((GATE_TIMEOUT / 60)) min. Still pending: $pending." >&2
            exit 1
        fi

        sleep "$POLL"
    done
}

# ---------------------------------------------------------------------------
# Stage 0b — CodeRabbit settle on HEAD (cap LA_WAIT_CR_SETTLE; best-effort)
# ---------------------------------------------------------------------------

# One poll for the cleared SHA $1. Sets OUTCOME to moved / reviewed / carried / rate-limited / paused / none and
# DETAIL to the new SHA (moved) or the evidence (reviewed).
cr_poll() {
    local cleared=$1 rc=0 all_ok=1 list statuses="" covered="" on_head=""
    OUTCOME=none
    DETAIL=""
    read_head || rc=$?
    if (( rc == 1 )); then
        return
    fi
    if [[ "$HEAD_SHA" != "$cleared" ]]; then
        OUTCOME=moved
        DETAIL=$HEAD_SHA
        return
    fi
    (( rc == 0 )) || all_ok=0

    # HEAD's CodeRabbit status descriptions, lowercased, newest first.
    if ! { list=$(rb_list "repos/$REPO/commits/$cleared/statuses" '.[]' 2>/dev/null) \
        && statuses=$(jq -c 'map(select(.context // "" | test("coderabbit"; "i")) | .description // "" | ascii_downcase)' \
            <<<"$list" 2>/dev/null); }; then
        statuses=""
        all_ok=0
    fi
    if ! { list=$(rb_list "repos/$REPO/issues/$PR/comments" '.[]' 2>/dev/null) \
        && covered=$(jq -r --arg head "$cleared" 'any(.[];
                (.user.login // "" | test("coderabbitai"; "i"))
                and (.body // "" | contains("summarize by coderabbit.ai"))
                and any(.body | capture("final_review_risk_coverage:(?<marker>\\{[^}]*\\})")? | .marker
                        | fromjson? | .coveredCommitId; . == $head))' <<<"$list" 2>/dev/null); }; then
        covered=""
        all_ok=0
    fi
    if ! { list=$(rb_list "repos/$REPO/pulls/$PR/reviews" '.[]' 2>/dev/null) \
        && on_head=$(jq -r --arg head "$cleared" 'any(.[];
                (.user.login // "" | test("coderabbitai"; "i")) and .commit_id == $head
                and (.body // "" | test("\\S")))' <<<"$list" 2>/dev/null); }; then
        on_head=""
        all_ok=0
    fi

    if [[ -n "$statuses" && $(jq -r 'any(.[]; contains("review completed"))' <<<"$statuses") == "true" ]]; then
        OUTCOME=reviewed
        DETAIL='status "Review completed"'
    elif [[ "$covered" == "true" ]]; then
        OUTCOME=reviewed
        DETAIL="summary covers HEAD"
    elif [[ "$on_head" == "true" ]]; then
        OUTCOME=reviewed
        DETAIL="review on HEAD"
    elif (( all_ok )); then
        case $(jq -r 'first // ""' <<<"$statuses") in
            *"carried forward"*) OUTCOME=carried ;;
            *"rate limited"*) OUTCOME=rate-limited ;;
            *"paused"*) OUTCOME=paused ;;
            *) ;;
        esac
    fi
}

while :; do
    gate
    cleared=$HEAD_SHA
    short=${cleared:0:7}
    present=""
    start=$(date +%s)

    while :; do
        if [[ -z "$present" ]]; then
            present=$(rb_coderabbit "$PR" "$REPO" "$ROLLUP" 2>/dev/null) || present=""
            if [[ "$present" == "false" ]]; then
                echo "Stage 0b: CodeRabbit is not on this PR — skipping settle."
                exit 0
            fi
        fi
        if [[ "$present" == "true" ]]; then
            cr_poll "$cleared"
            case $OUTCOME in
                moved)
                    echo "Stage 0b: HEAD moved from $short to ${DETAIL:0:7} — restarting Stage 0a."
                    continue 2
                    ;;
                reviewed)
                    echo "Stage 0b: CodeRabbit reviewed HEAD $short ($DETAIL)."
                    exit 0
                    ;;
                carried)
                    echo "Stage 0b: CodeRabbit carried its prior review forward to HEAD $short."
                    exit 0
                    ;;
                rate-limited|paused)
                    if [[ "$OUTCOME" == "paused" ]]; then
                        echo "Stage 0b: CodeRabbit reviews are PAUSED — no review ran for HEAD $short." >&2
                    else
                        echo "Stage 0b: CodeRabbit is RATE LIMITED — no review ran for HEAD $short." >&2
                    fi
                    echo "Stage 0b: re-trigger with 'gh pr comment $PR --repo $REPO --body \"@coderabbitai review\"' once the window clears." >&2
                    exit 3
                    ;;
                *) ;;
            esac
        fi

        elapsed=$(( $(date +%s) - start ))
        if (( elapsed >= CR_SETTLE )); then
            echo "Stage 0b: hit $((CR_SETTLE / 60))m cap without CodeRabbit evidence for HEAD $short — proceeding anyway." >&2
            exit 0
        fi

        echo "Stage 0b: waiting for CodeRabbit on HEAD $short (elapsed $((elapsed / 60))m). Sleeping ${CR_POLL}s."
        sleep "$CR_POLL"
    done
done
