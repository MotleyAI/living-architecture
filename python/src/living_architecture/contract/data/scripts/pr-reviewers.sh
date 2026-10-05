#!/usr/bin/env bash
# Report which review bots ran on a PR, as one JSON document:
#   {"coderabbit": <bool>, "sonar": {"present": <bool>, "project_key": <string|null>}}
#
# Usage:
#   la-pr-reviewers <PR_NUMBER> [--repo OWNER/REPO]
#
# Exits 0, or 2 on a usage or gh error (no JSON printed).

set -euo pipefail

# shellcheck source=review-bots.bash
source "$(dirname "${BASH_SOURCE[0]}")/review-bots.bash"

usage() {
    cat >&2 <<EOF
usage: la-pr-reviewers <PR_NUMBER> [--repo OWNER/REPO]

  <PR_NUMBER>           required, the PR number
  --repo OWNER/REPO     optional, defaults to the repo of the current git directory
EOF
    exit 2
}

PR=""
REPO=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --repo)
            [[ $# -ge 2 ]] || usage
            REPO="$2"
            shift 2
            ;;
        -h|--help)
            usage
            ;;
        -*)
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

if [[ ! "$PR" =~ ^[0-9]+$ ]]; then
    usage
fi

if [[ -z "$REPO" ]]; then
    REPO=$(gh repo view --json nameWithOwner --jq '.nameWithOwner' 2>/dev/null \
        || { echo "could not resolve --repo from gh repo view" >&2; exit 2; })
fi

rollup=$(rb_rollup "$PR" "$REPO") || exit 2
coderabbit=$(rb_coderabbit "$PR" "$REPO" "$rollup") || exit 2
sonar_check=$(rb_sonar_check "$rollup")
key=""
if [[ -n "$sonar_check" ]]; then
    key=$(rb_sonar_key "$sonar_check") || exit 2
fi

jq -nc --argjson coderabbit "$coderabbit" --arg present "$([[ -n "$sonar_check" ]] && echo true || echo false)" \
    --arg key "$key" \
    '{coderabbit: $coderabbit, sonar: {present: ($present == "true"), project_key: (if $key == "" then null else $key end)}}'
