# Review-bot detection shared by pr-reviewers.sh and wait-for-reviews.sh (sourced, never run).
# A bot is a fact of the PR: CodeRabbit by a status check or any comment of its bot; Sonar by a check whose
# name contains "sonar" (case-insensitive).

# The PR's status-check rollup as a JSON array; fails when gh does.
rb_rollup() {
    gh pr view "$1" --repo "$2" --json statusCheckRollup --jq '.statusCheckRollup'
}

# "true" when CodeRabbit is on the PR (rollup JSON in $3); fails when gh does.
rb_coderabbit() {
    local by_status by_comment
    by_status=$(jq -r 'any(.[]; (.context // .name // "") | ascii_downcase | test("coderabbit"))' <<<"$3") || return 1
    if [[ "$by_status" == "true" ]]; then
        echo true
        return
    fi
    by_comment=$(gh api --paginate "repos/$2/issues/$1/comments" --jq '.[] | select(.user.login | test("coderabbitai"; "i")) | .user.login') || return 1
    if [[ -n "$by_comment" ]]; then echo true; else echo false; fi
}

# The first Sonar check of the rollup JSON in $1, as JSON; empty when there is none.
rb_sonar_check() {
    jq -c 'map(select((.context // .name // "") | ascii_downcase | test("sonar"))) | first // empty' <<<"$1"
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
