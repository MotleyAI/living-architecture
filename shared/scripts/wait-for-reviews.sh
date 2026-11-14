#!/usr/bin/env bash
# Watch a PR until CodeRabbit, Sonar and CI are terminal on HEAD, printing each new review item once on stdout.
#
# Every LA_WAIT_POLL_SECONDS one poll reads HEAD's snapshot (SHA + status-check rollup), HEAD's Sonar check suites
# and, when CodeRabbit is on the PR (as la-pr-reviewers detects it), its evidence and comments. Items, one stdout
# line each, never the same key twice (the keys persist per PR in the git dir):
#   ci-failed <sha7> <url> <name>         a failed check on HEAD other than CodeRabbit's or Sonar's
#   coderabbit-comment <url>              a CodeRabbit PR review comment (thread or reply)
#   coderabbit-review <url>               a CodeRabbit PR review with a body
#   sonar-done <sha7> <conclusion>        every Sonar suite and check on HEAD finished
#   coderabbit-settled <sha7> <outcome>   reviewed / carried-forward / rate-limited / paused / cap
#   head-moved <old7> <new7>              HEAD changed since the previous poll; the gate and settle restart
# Progress and diagnostics go to stderr.
#
# The gate is clear when no check is PENDING / EXPECTED / QUEUED / IN_PROGRESS / WAITING / REQUESTED and every Sonar
# suite is `completed`; a failed read keeps it pending. CodeRabbit is reviewed (wins) on a status on HEAD described
# "Review completed", the summary comment's (`summarize by coderabbit.ai`) coverage marker naming HEAD, or a review
# on HEAD with a body; otherwise, from a poll whose reads all succeeded, HEAD's latest CodeRabbit status: "Prior
# review carried forward", "Review rate limited" or "Review paused".
#
# Env: LA_WAIT_GATE_TIMEOUT (gate cap, seconds, default 1800), LA_WAIT_POLL_SECONDS (poll, default 60),
#      LA_WAIT_CR_SETTLE (CodeRabbit cap after the gate clears, seconds, default 600).
#
# Exits, once the gate is clear: 0 when CodeRabbit reviewed or carried forward HEAD, is not on the PR, or its cap ran
# out; 3 when it is rate limited or paused on HEAD. 1 on the gate timeout, 2 when the repo can't be resolved, 64 on
# usage.
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

CR_LOGIN='test("coderabbitai"; "i")'
CR_OR_SONAR='(.context // .name // "") | ascii_downcase | test("coderabbit|sonar")'
NON_TERMINAL='(.__typename == "StatusContext" and (.state == "PENDING" or .state == "EXPECTED"))
    or ((.__typename == "CheckRun" or .__typename == "WorkflowRun")
        and (.status == "QUEUED" or .status == "IN_PROGRESS" or .status == "WAITING" or .status == "REQUESTED"
             or .status == "PENDING"))'

# ---------------------------------------------------------------------------
# Printed keys: this run's in SEEN, every run's in the state file
# ---------------------------------------------------------------------------

declare -A SEEN=()
STATE_WARNED=0
if STATE=$(git rev-parse --git-path "la/reviews/$REPO/$PR.json" 2>/dev/null); then
    :
else
    STATE=""
    echo "Not in a git repository: printed items are not persisted beyond this run." >&2
fi

# Adds the state file's keys to SEEN; a missing file is empty, an unreadable or malformed one warns once.
state_read() {
    local keys key
    [[ -n "$STATE" && -e "$STATE" ]] || return 0
    if ! keys=$(jq -r '(.printed // []) | if type == "array" then .[] | strings else error end' "$STATE" 2>/dev/null); then
        if (( ! STATE_WARNED )); then
            echo "warning: ignoring the unreadable state file $STATE" >&2
            STATE_WARNED=1
        fi
        return 0
    fi
    while IFS= read -r key; do
        [[ -n "$key" ]] && SEEN[$key]=1
    done <<<"$keys"
    return 0
}

# Re-reads the state file and replaces it atomically with its union with SEEN; a failed write warns.
state_write() {
    local tmp=""
    [[ -n "$STATE" ]] || return 0
    state_read
    if mkdir -p "$(dirname "$STATE")" 2>/dev/null && tmp=$(mktemp "$STATE.XXXXXX" 2>/dev/null) \
        && printf '%s\n' "${!SEEN[@]}" | jq -Rnc '{printed: [inputs | select(. != "")] | unique}' >"$tmp" \
        && mv -f "$tmp" "$STATE"; then
        return 0
    fi
    [[ -n "$tmp" ]] && rm -f "$tmp"
    echo "warning: could not write the state file $STATE; its items may be printed again by a later run." >&2
}

# Prints each "<key>\t<line>" of $1 whose key is unseen, then records the keys.
emit() {
    local items=$1 key line new=0
    while IFS=$'\t' read -r key line; do
        [[ -n "$key" && -z "${SEEN[$key]:-}" ]] || continue
        SEEN[$key]=1
        printf '%s\n' "$line"
        new=1
    done <<<"$items"
    if (( new )); then
        state_write
    fi
}

# ---------------------------------------------------------------------------
# One poll
# ---------------------------------------------------------------------------

# HEAD's snapshot into HEAD_SHA and ROLLUP, then its Sonar suites into SUITES. Returns 1 when the snapshot read
# fails, 2 when the suites read does.
read_head() {
    local snapshot
    snapshot=$(rb_snapshot "$PR" "$REPO" 2>/dev/null) || return 1
    HEAD_SHA=$(jq -r '.headRefOid' <<<"$snapshot")
    ROLLUP=$(jq -c '.statusCheckRollup' <<<"$snapshot")
    SUITES=$(rb_sonar_suites "$HEAD_SHA" "$REPO" 2>/dev/null) || return 2
}

# The ci-failed items of ROLLUP, as "<key>\t<line>" lines.
ci_items() {
    jq -r --arg sha "$HEAD_SHA" --arg short "${HEAD_SHA:0:7}" '.[]
        | select((('"$CR_OR_SONAR"') | not)
            and ((.conclusion // .state // "") | ascii_upcase
                 | IN("FAILURE", "TIMED_OUT", "CANCELLED", "ACTION_REQUIRED", "STARTUP_FAILURE", "ERROR")))
        | (.name // .context // "?") as $name
        | (.detailsUrl // .targetUrl // "") as $url
        | (if .__typename == "StatusContext" then
              if .startedAt then "ci \($sha) status \($name) \(.startedAt)" else "ci \($sha) status \($name) \($url)" end
           elif $url != "" then "ci \($sha) url \($url)"
           else "ci \($sha) name \($name)" end) as $key
        | "\($key)\tci-failed \($short) \(if $url == "" then "-" else $url end) \($name)"' <<<"$ROLLUP"
}

# The sonar-done item when HEAD has a Sonar suite, every one completed, and no Sonar check in ROLLUP is pending.
sonar_item() {
    jq -r --arg sha "$HEAD_SHA" --arg short "${HEAD_SHA:0:7}" --argjson rollup "$ROLLUP" '
        select(length > 0 and all(.[]; (.status // "" | ascii_downcase) == "completed")
            and ([$rollup[] | select(((.context // .name // "") | ascii_downcase | test("sonar"))
                                    and ('"$NON_TERMINAL"'))] | length == 0))
        | (first(.[] | .conclusion // "unknown" | select(. != "success")) // "success") as $conclusion
        | "sonar \($sha)\tsonar-done \($short) \($conclusion)"' <<<"$SUITES"
}

# CodeRabbit on HEAD: sets OUTCOME to reviewed / carried-forward / rate-limited / paused / none, DETAIL to the
# evidence, and CR_ITEMS to its comment and review items. $1 is 1 when every earlier read of the poll succeeded.
cr_poll() {
    local all_ok=$1 list statuses="" covered="" on_head="" comments="" reviews=""
    OUTCOME=none
    DETAIL=""
    CR_ITEMS=""

    # HEAD's CodeRabbit status descriptions, lowercased, newest first.
    if ! { list=$(rb_list "repos/$REPO/commits/$HEAD_SHA/statuses" '.[]' 2>/dev/null) \
        && statuses=$(jq -c 'map(select(.context // "" | test("coderabbit"; "i")) | .description // "" | ascii_downcase)' \
            <<<"$list" 2>/dev/null); }; then
        statuses=""
        all_ok=0
    fi
    if ! { list=$(rb_list "repos/$REPO/issues/$PR/comments" '.[]' 2>/dev/null) \
        && covered=$(jq -r --arg head "$HEAD_SHA" 'any(.[];
                (.user.login // "" | '"$CR_LOGIN"')
                and (.body // "" | contains("summarize by coderabbit.ai"))
                and any(.body | capture("final_review_risk_coverage:(?<marker>\\{[^}]*\\})")? | .marker
                        | fromjson? | .coveredCommitId; . == $head))' <<<"$list" 2>/dev/null); }; then
        covered=""
        all_ok=0
    fi
    if ! { list=$(rb_list "repos/$REPO/pulls/$PR/reviews" '.[]' 2>/dev/null) \
        && reviews=$(jq -c 'map(select((.user.login // "" | '"$CR_LOGIN"') and (.body // "" | test("\\S"))))' \
            <<<"$list" 2>/dev/null) \
        && on_head=$(jq -r --arg head "$HEAD_SHA" 'any(.[]; .commit_id == $head)' <<<"$reviews"); }; then
        reviews=""
        on_head=""
        all_ok=0
    fi
    if ! { list=$(rb_list "repos/$REPO/pulls/$PR/comments" '.[]' 2>/dev/null) \
        && comments=$(jq -r '.[] | select(.user.login // "" | '"$CR_LOGIN"')
                | "coderabbit-comment \(.id)\tcoderabbit-comment \(.html_url)"' <<<"$list" 2>/dev/null); }; then
        comments=""
        all_ok=0
    fi
    CR_ITEMS=$comments
    if [[ -n "$reviews" ]]; then
        CR_ITEMS+=$'\n'$(jq -r '.[] | "coderabbit-review \(.id)\tcoderabbit-review \(.html_url)"' <<<"$reviews")
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
            *"carried forward"*) OUTCOME=carried-forward ;;
            *"rate limited"*) OUTCOME=rate-limited ;;
            *"paused"*) OUTCOME=paused ;;
            *) ;;
        esac
    fi
}

settled_item() {
    printf 'coderabbit-settled %s %s\tcoderabbit-settled %s %s' "$HEAD_SHA" "$1" "${HEAD_SHA:0:7}" "$1"
}

# ---------------------------------------------------------------------------
# The loop
# ---------------------------------------------------------------------------

state_read
prev=""
present=""
start=$(date +%s)
cleared_at=""

while :; do
    rc=0
    read_head || rc=$?
    OUTCOME=none
    if (( rc == 1 )); then
        pending="(unknown — could not read the check rollup)"
    else
        short=${HEAD_SHA:0:7}
        if [[ -n "$prev" && "$HEAD_SHA" != "$prev" ]]; then
            printf 'head-moved %s %s\n' "${prev:0:7}" "$short"
            echo "HEAD moved from ${prev:0:7} to $short — restarting the gate and the CodeRabbit settle." >&2
            start=$(date +%s)
            cleared_at=""
        fi
        prev=$HEAD_SHA

        pending=$(jq -r '[.[] | select('"$NON_TERMINAL"') | (.name // .context)] | join(", ")' <<<"$ROLLUP")
        if (( rc == 2 )); then
            pending="${pending:+$pending, }(unknown — could not read the check suites)"
        else
            pending=$(jq -r --arg rollup "$pending" '[($rollup | select(. != "")),
                (.[] | select((.status // "" | ascii_downcase) != "completed") | "\(.app.slug) (check suite)")]
                | join(", ")' <<<"$SUITES")
        fi

        if [[ "$present" != "true" ]]; then
            present=$(rb_coderabbit "$PR" "$REPO" "$ROLLUP" 2>/dev/null) || present=""
        fi
        items=$(ci_items)
        if [[ "$present" == "true" ]]; then
            cr_poll "$(( rc == 0 ))"
            items+=$'\n'$CR_ITEMS
        fi
        if (( rc == 0 )); then
            items+=$'\n'$(sonar_item)
        fi
        if [[ "$OUTCOME" != "none" ]]; then
            items+=$'\n'$(settled_item "$OUTCOME")
        fi
        state_read
        emit "$items"
    fi

    now=$(date +%s)
    if [[ -n "$pending" ]]; then
        cleared_at=""
        elapsed=$(( now - start ))
        if (( elapsed >= GATE_TIMEOUT )); then
            echo "Stage 0a: gate timed out after $((GATE_TIMEOUT / 60)) min. Still pending: $pending." >&2
            exit 1
        fi
        echo "Stage 0a: pending — $pending (elapsed $((elapsed / 60))m). Sleeping ${POLL}s." >&2
        sleep "$POLL"
        continue
    fi

    if [[ -z "$cleared_at" ]]; then
        cleared_at=$now
        echo "Stage 0a: gate clear." >&2
    fi
    case $OUTCOME in
        reviewed)
            echo "Stage 0b: CodeRabbit reviewed HEAD $short ($DETAIL)." >&2
            exit 0
            ;;
        carried-forward)
            echo "Stage 0b: CodeRabbit carried its prior review forward to HEAD $short." >&2
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
    if [[ "$present" == "false" ]]; then
        echo "Stage 0b: CodeRabbit is not on this PR — skipping settle." >&2
        exit 0
    fi

    elapsed=$(( now - cleared_at ))
    if (( elapsed >= CR_SETTLE )); then
        emit "$(settled_item cap)"
        echo "Stage 0b: hit $((CR_SETTLE / 60))m cap without CodeRabbit evidence for HEAD $short — proceeding anyway." >&2
        exit 0
    fi
    echo "Stage 0b: waiting for CodeRabbit on HEAD $short (elapsed $((elapsed / 60))m). Sleeping ${POLL}s." >&2
    sleep "$POLL"
done
