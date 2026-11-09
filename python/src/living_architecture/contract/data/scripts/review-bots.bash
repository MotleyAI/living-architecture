# Review-bot detection shared by pr-reviewers.sh and wait-for-reviews.sh (sourced, never run).
# A bot is a fact of the PR: CodeRabbit by a status check or any comment of its bot; Sonar by a check whose
# name contains "sonar", or a check suite on HEAD whose app slug does (both case-insensitive). Every read keyed to
# HEAD takes its SHA from one snapshot. Every helper fails (non-zero) when gh does or its output is malformed.

# The PR's HEAD snapshot: {"headRefOid": <sha>, "statusCheckRollup": [...]}, both read in one call.
rb_snapshot() {
    local out
    out=$(gh pr view "$1" --repo "$2" --json headRefOid,statusCheckRollup) || return 1
    jq -ce 'select(.headRefOid | type == "string")
        | {headRefOid, statusCheckRollup: (.statusCheckRollup // [])}' <<<"$out"
}

# A paginated list endpoint ($1) as one JSON array of the items $2 picks from each page.
rb_list() {
    local items
    items=$(gh api --paginate "$1" --jq "$2") || return 1
    jq -cs . <<<"$items"
}

# The Sonar check suites of commit $1 in repo $2, as a JSON array.
rb_sonar_suites() {
    local suites
    suites=$(rb_list "repos/$2/commits/$1/check-suites" '.check_suites[]') || return 1
    jq -c 'map(select(.app.slug // "" | ascii_downcase | test("sonar")))' <<<"$suites"
}

# "true" when CodeRabbit is on the PR (rollup JSON in $3).
rb_coderabbit() {
    local by_status comments
    by_status=$(jq -r 'any(.[]; (.context // .name // "") | ascii_downcase | test("coderabbit"))' <<<"$3") || return 1
    if [[ "$by_status" == "true" ]]; then
        echo true
        return
    fi
    comments=$(rb_list "repos/$2/issues/$1/comments" '.[]') || return 1
    jq -r 'any(.[]; .user.login // "" | test("coderabbitai"; "i"))' <<<"$comments"
}

# The first Sonar check of the rollup JSON in $1, as JSON; empty when there is none.
rb_sonar_check() {
    local rollup=$1
    jq -c 'map(select((.context // .name // "") | ascii_downcase | test("sonar"))) | first // empty' <<<"$rollup"
    return
}

# The Sonar project key: config, then sonar-project.properties, then the check URL's `id`; empty when none.
rb_sonar_key() {
    local key root
    key=$(la-config get reviewers.sonar.project_key) || return 1
    if [[ -z "$key" ]]; then
        root=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
        if [[ -f "$root/sonar-project.properties" ]]; then
            key=$(sed -nE 's/^[[:space:]]*sonar\.projectKey[[:space:]]*[=:][[:space:]]*(.*[^[:space:]])[[:space:]]*$/\1/p' \
                "$root/sonar-project.properties" | head -n 1)
        fi
    fi
    if [[ -z "$key" ]]; then
        key=$(jq -r '(.detailsUrl // .targetUrl // "") | capture("[?&]id=(?<id>[^&#]+)").id // empty' <<<"$1")
    fi
    printf '%s' "$key"
}
