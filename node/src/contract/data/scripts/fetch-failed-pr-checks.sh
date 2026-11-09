#!/usr/bin/env bash
# Fetch failed CI checks on a GitHub PR and (for GitHub Actions) a log excerpt of each.
# Always emits Markdown to stdout AND writes the full filtered JSON to a tempfile.
set -euo pipefail

usage() {
    cat >&2 <<EOF
usage: la-fetch-failed-pr-checks <PR_NUMBER> [--repo OWNER/REPO] [--max-log-lines N]

  <PR_NUMBER>          required, the PR number
  --repo OWNER/REPO    optional, defaults to the current repo via gh repo view
  --max-log-lines N    tail each failed job's log excerpt at N lines (default: 200); a job-log API excerpt also keeps the earlier ##[error] lines

Output: Markdown to stdout, full JSON to \${TMPDIR:-/tmp}/failed-pr-checks-<pr>-<ts>.json.
EOF
    exit 2
}

PR=""
REPO=""
MAX_LOG=200

while [[ $# -gt 0 ]]; do
    case "$1" in
        --repo)
            [[ $# -ge 2 ]] || usage
            REPO="$2"; shift 2 ;;
        --repo=*)
            REPO="${1#--repo=}"; shift ;;
        --max-log-lines)
            [[ $# -ge 2 ]] || usage
            MAX_LOG="$2"; shift 2 ;;
        --max-log-lines=*)
            MAX_LOG="${1#--max-log-lines=}"; shift ;;
        -h|--help)
            usage ;;
        --)
            shift; break ;;
        -*)
            echo "error: unknown flag: $1" >&2
            usage ;;
        *)
            if [[ -z "$PR" ]]; then
                PR="$1"; shift
            else
                echo "error: unexpected positional arg: $1" >&2
                usage
            fi
            ;;
    esac
done

[[ -n "$PR" ]] || usage
[[ "$PR"     =~ ^[0-9]+$ ]] || { echo "error: PR_NUMBER must be a positive integer, got: $PR" >&2; exit 2; }
[[ "$MAX_LOG" =~ ^[0-9]+$ ]] || { echo "error: --max-log-lines must be a non-negative integer, got: $MAX_LOG" >&2; exit 2; }

if [[ -z "$REPO" ]]; then
    REPO="$(gh repo view --json owner,name -q '.owner.login + "/" + .name' 2>/dev/null || true)"
    [[ -n "$REPO" ]] || { echo "error: --repo not given and could not auto-detect (cwd is not a gh-recognised repo)" >&2; exit 2; }
fi

command -v gh >/dev/null 2>&1 || { echo "error: gh is required" >&2; exit 127; }
command -v jq >/dev/null 2>&1 || { echo "error: jq is required" >&2; exit 127; }

# Pull the full statusCheckRollup. Three node typenames appear here:
# - CheckRun       (GitHub Actions): .conclusion, .name, .detailsUrl, .workflowName
# - StatusContext  (legacy / external CI): .state, .context, .targetUrl
# - WorkflowRun    (rare): treated like CheckRun via fallback fields
all_checks="$(gh pr view "$PR" --repo "$REPO" --json statusCheckRollup -q '.statusCheckRollup // []')"

# Normalise + filter to non-passing terminal states.
failed="$(echo "$all_checks" | jq '[
    .[]
    | (.conclusion // .state // "") as $c
    | select(($c | ascii_upcase) | IN("FAILURE","TIMED_OUT","CANCELLED","ACTION_REQUIRED","STARTUP_FAILURE","ERROR"))
    | {
        typename:      .__typename,
        name:          (.name // .context // null),
        workflow_name: (.workflowName // null),
        conclusion:    (.conclusion // .state // null),
        status:        (.status // null),
        details_url:   (.detailsUrl // .targetUrl // null),
        completed_at:  (.completedAt // null)
    }
]')"

# One temp dir per run; the final JSON lives outside it.
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
enriched_file="$work/enriched.json"
echo '[]' > "$enriched_file"

BOM="$(printf '\357\273\277')"
# The job's first step whose conclusion is not success, skipped, neutral or null, as "<start> <end>" to the second.
FAILED_STEP_JQ='first(.steps[] | select(.conclusion as $c | $c != null and $c != "success" and $c != "skipped" and $c != "neutral")) | "\(.started_at[0:19]) \(.completed_at[0:19])"'

# Runs gh with stdout and stderr to files; sets rc.
run_gh() {
    local out="$1" err="$2"
    shift 2
    if gh "$@" >"$out" 2>"$err"; then rc=0; else rc=$?; fi
}

# Why a call gave no log: its last non-empty stderr line, else its exit code, else "empty log".
failure_reason() {
    local err="$1" reason
    reason="$(awk 'NF { last = $0 } END { print last }' "$err")"
    if [[ -n "$reason" ]]; then echo "$reason"
    elif [[ "$rc" -ne 0 ]]; then echo "exit $rc"
    else echo "empty log"
    fi
}

has_log() {
    local file="$1"
    LC_ALL=C grep -q '[^[:space:]]' "$file"
}

record() {
    local command="$1" outcome="$2"
    jq -nc --arg command "$command" --arg outcome "$outcome" '{command: $command, outcome: $outcome}' >> "$attempts"
}

# The failed step's section: log lines stamped within [start, end] to the second (an unstamped line takes the
# previous stamp), from the first `##[group]Run ` line to the last `##[error]` line and its unstamped continuation.
step_section() {
    local log="$1" start="$2" end="$3"
    LC_ALL=C awk -v s="$start" -v e="$end" '
        function is_error(l) { return index(l, "##[error]") == 1 || index(l, " ##[error]") > 0 }
        function is_run(l) { return index(l, "##[group]Run ") == 1 || index(l, " ##[group]Run ") > 0 }
        { stamped = 0 }
        /^[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]/ { ts = substr($0, 1, 19); stamped = 1 }
        ts != "" && (ts "") >= (s "") && (ts "") <= (e "") { line[++n] = $0; own[n] = stamped }
        END {
            first = 1
            for (i = 1; i <= n; i++) if (is_run(line[i])) { first = i; break }
            last = n
            for (i = n; i >= first; i--) if (is_error(line[i])) { last = i; break }
            while (last < n && !own[last + 1]) last++
            for (i = first; i <= last; i++) print line[i]
        }' "$log"
}

# The `##[error]` lines before the last N lines, then the last N lines; each gap one omitted-lines line.
errors_and_tail() {
    local log="$1"
    LC_ALL=C awk -v n="$MAX_LOG" '
        function is_error(l) { return index(l, "##[error]") == 1 || index(l, " ##[error]") > 0 }
        { line[NR] = $0 }
        END {
            cut = NR - n
            last = 0
            for (i = 1; i <= cut; i++) {
                if (!is_error(line[i])) continue
                if (i > last + 1) print "[... " (i - last - 1) " lines omitted ...]"
                print line[i]
                last = i
            }
            if (cut > last) print "[... " (cut - last) " lines omitted ...]"
            for (i = (cut > 0 ? cut + 1 : 1); i <= NR; i++) print line[i]
        }' "$log"
}

# Job-log API attempt for a job id: sets source and writes the excerpt.
api_excerpt() {
    local job="$1"
    local logs="repos/$REPO/actions/jobs/$job/logs" meta="repos/$REPO/actions/jobs/$job" outcome start end
    local section="$work/log"
    run_gh "$work/out" "$work/err" api "$logs"
    if ! has_log "$work/out"; then
        record "gh api $logs" "$(failure_reason "$work/err")"
        return
    fi
    record "gh api $logs" ok
    LC_ALL=C awk -v bom="$BOM" 'NR == 1 && substr($0, 1, 3) == bom { $0 = substr($0, 4) } { print }' \
        "$work/out" > "$work/log"
    source=api-errors-tail
    run_gh "$work/meta" "$work/err" api "$meta" --jq "$FAILED_STEP_JQ"
    if [[ "$rc" -ne 0 ]]; then
        outcome="$(failure_reason "$work/err")"
    elif ! read -r start end < "$work/meta"; then
        outcome="no failed step"
    else
        step_section "$work/log" "$start" "$end" > "$work/section"
        if [[ -s "$work/section" ]]; then
            outcome=ok
            source=api-step
            section="$work/section"
        else
            outcome="no log lines in the step's time window"
        fi
    fi
    record "gh api $meta" "$outcome"
    errors_and_tail "$section" > "$excerpt"
}

# Enrich each failed check with run_id / job_id / log excerpt and how it was obtained
# (only resolvable when the details URL is a GitHub Actions URL we recognise).
n=$(echo "$failed" | jq 'length')
i=0
while [[ "$i" -lt "$n" ]]; do
    check="$(echo "$failed" | jq -c ".[$i]")"
    url="$(echo "$check" | jq -r '.details_url // ""')"
    run_id=""
    job_id=""
    source=""
    attempts="$work/attempts"
    excerpt="$work/excerpt"
    : > "$attempts"
    : > "$excerpt"

    if [[ "$url" =~ /actions/runs/([0-9]+) ]]; then
        run_id="${BASH_REMATCH[1]}"
    fi
    if [[ "$url" =~ /job/([0-9]+) ]]; then
        job_id="${BASH_REMATCH[1]}"
    fi

    if [[ "$MAX_LOG" -gt 0 ]] && [[ -n "$run_id" ]]; then
        if [[ -n "$job_id" ]]; then target=(--job "$job_id"); else target=("$run_id"); fi
        # `--log-failed` emits only steps GitHub marked as failed; a job can fail with none (a service
        # container that never came up, a runner-level abort), so the full log's tail comes next.
        for flag in --log-failed --log; do
            run_gh "$work/out" "$work/err" run view "${target[@]}" --repo "$REPO" "$flag"
            if has_log "$work/out"; then
                record "gh run view ${target[*]} $flag" ok
                tail -n "$MAX_LOG" "$work/out" > "$excerpt"
                source="${flag#--}"
                break
            fi
            record "gh run view ${target[*]} $flag" "$(failure_reason "$work/err")"
        done
        # Both can be empty for a plain Actions job whose log GitHub still serves through the REST API.
        if [[ -z "$source" ]] && [[ -n "$job_id" ]]; then
            api_excerpt "$job_id"
        fi
    fi

    jq -n \
        --slurpfile cur "$enriched_file" \
        --argjson check "$check" \
        --arg run_id "$run_id" \
        --arg job_id "$job_id" \
        --rawfile log "$excerpt" \
        --arg source "$source" \
        --slurpfile attempts "$attempts" \
        '$cur[0] + [$check + {run_id: $run_id, job_id: $job_id, log_excerpt: $log,
                              log_source: (if $source == "" then null else $source end), log_attempts: $attempts}]' \
        > "$enriched_file.tmp"
    mv "$enriched_file.tmp" "$enriched_file"

    i=$((i + 1))
done

ts="$(date -u +%Y%m%d-%H%M%S)"
json_out="${TMPDIR:-/tmp}/failed-pr-checks-${PR}-${ts}.json"
jq -n \
    --argjson pr "$PR" \
    --arg repo "$REPO" \
    --slurpfile failed "$enriched_file" \
    '{pr: $pr, repo: $repo, failed_checks: $failed[0]}' \
    > "$json_out"

# Markdown
echo "# Failed CI checks on $REPO PR #$PR"
echo
fail_count=$(jq 'length' "$enriched_file")
if [[ "$fail_count" = "0" ]]; then
    echo "_No failed checks._"
    echo
else
    jq -r --argjson max "$MAX_LOG" '
        to_entries[]
        | (.key + 1) as $i
        | .value as $c
        | (
            "## Check \($i) — \(($c.workflow_name // "") + (if ($c.workflow_name // "") != "" and ($c.name // "") != "" then " / " else "" end) + ($c.name // "?"))",
            "Conclusion: \($c.conclusion)   Status: \($c.status // "n/a")   Type: \($c.typename // "?")",
            "Details: \($c.details_url // "n/a")",
            (if ($c.run_id // "") != "" then "Run: \($c.run_id)\(if ($c.job_id // "") != "" then "  Job: \($c.job_id)" else "" end)" else empty end),
            "",
            (if ($c.log_excerpt // "") != "" then
                "<details><summary>\({
                    "log-failed": "Failed-step log (last \($max) lines)",
                    "log": "Full log (last \($max) lines)",
                    "api-step": "Failed-step log from the job-log API (##[error] lines + last \($max) lines)",
                    "api-errors-tail": "Job log from the job-log API (##[error] lines + last \($max) lines)"
                }[$c.log_source])</summary>",
                "",
                "```",
                $c.log_excerpt,
                "```",
                "",
                "</details>"
             elif $max == 0 then
                "_No log excerpt: log fetching is off (--max-log-lines 0)._"
             elif ($c.run_id // "") == "" then
                "_No log excerpt available — likely an external CI; follow Details URL._"
             else
                "_No log excerpt — every attempt failed:_",
                ($c.log_attempts[] | "- `\(.command)`: \(.outcome)")
             end),
            "",
            "---",
            ""
          )
    ' "$enriched_file"
fi

echo "JSON: $json_out"
