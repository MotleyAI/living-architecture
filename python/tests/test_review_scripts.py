import json
import re
from pathlib import Path

REPO = ["--repo", "o/r"]


def _json_path(stdout: str) -> Path:
    m = re.search(r"^JSON: (.+)$", stdout, re.MULTILINE)
    assert m, stdout
    return Path(m.group(1))


# --------------------------------------------------------------------------- reply-to-pr-thread


def test_reply_parses_discussion_url(fake_gh, run_script):
    fake_gh.route((["api", "POST"], {"html_url": "https://github.com/o/r/pull/5#discussion_r999"}))
    r = run_script("reply-to-pr-thread.sh", "https://github.com/o/r/pull/5#discussion_r123", stdin="hello\n")
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "https://github.com/o/r/pull/5#discussion_r999"
    [call] = fake_gh.calls()
    assert "repos/o/r/pulls/5/comments/123/replies" in call["argv"]
    assert json.loads(call["input"]) == {"body": "hello\n"}


def test_reply_with_explicit_ids(fake_gh, run_script):
    fake_gh.route((["api", "POST"], {"html_url": "u"}))
    r = run_script("reply-to-pr-thread.sh", "--comment-id", "9", "--pr", "3", *REPO, stdin="x")
    assert r.returncode == 0, r.stderr
    assert "repos/o/r/pulls/3/comments/9/replies" in fake_gh.calls()[0]["argv"]


def test_reply_rejects_review_summary_url(run_script):
    r = run_script("reply-to-pr-thread.sh", "https://github.com/o/r/pull/5#pullrequestreview-1", stdin="x")
    assert r.returncode == 2
    assert "review-summary" in r.stderr


def test_reply_rejects_empty_body(fake_gh, run_script):
    r = run_script("reply-to-pr-thread.sh", "https://github.com/o/r/pull/5#discussion_r1", stdin="")
    assert r.returncode == 2
    assert fake_gh.calls() == []


def test_reply_invalid_coderabbit_prepends_mention(fake_gh, run_script):
    fake_gh.route((["api", "POST"], {"html_url": "u"}))
    r = run_script("reply-invalid-coderabbit.sh", "https://github.com/o/r/pull/5#discussion_r1", stdin="not a bug")
    assert r.returncode == 0, r.stderr
    assert json.loads(fake_gh.calls()[0]["input"])["body"] == "@coderabbitai not a bug"


def test_reply_invalid_coderabbit_keeps_existing_mention(fake_gh, run_script):
    fake_gh.route((["api", "POST"], {"html_url": "u"}))
    run_script("reply-invalid-coderabbit.sh", "https://github.com/o/r/pull/5#discussion_r1", stdin="@coderabbitai ok")
    assert json.loads(fake_gh.calls()[0]["input"])["body"] == "@coderabbitai ok"


# --------------------------------------------------------------------------- fetch-failed-pr-checks

ROLLUP = {
    "statusCheckRollup": [
        {"__typename": "CheckRun", "name": "tests", "workflowName": "CI", "conclusion": "FAILURE",
         "status": "COMPLETED", "detailsUrl": "https://github.com/o/r/actions/runs/11/job/22"},
        {"__typename": "CheckRun", "name": "lint", "workflowName": "CI", "conclusion": "SUCCESS",
         "status": "COMPLETED", "detailsUrl": "https://github.com/o/r/actions/runs/11/job/23"},
        {"__typename": "StatusContext", "context": "ext-ci", "state": "ERROR", "targetUrl": "https://ci.example/1"},
    ]
}


def test_failed_checks_with_logs(fake_gh, run_script):
    fake_gh.route(
        (["pr", "view", "statusCheckRollup"], ROLLUP),
        (["run", "view", "--job", "22", "--log-failed"], "step: boom\n"),
    )
    r = run_script("fetch-failed-pr-checks.sh", "7", *REPO)
    assert r.returncode == 0, r.stderr
    assert "## Check 1 — CI / tests" in r.stdout
    assert "step: boom" in r.stdout
    assert "## Check 2 — ext-ci" in r.stdout
    assert "_No log excerpt available" in r.stdout
    assert "lint" not in r.stdout
    data = json.loads(_json_path(r.stdout).read_text())
    assert [c["name"] for c in data["failed_checks"]] == ["tests", "ext-ci"]
    assert data["failed_checks"][0]["job_id"] == "22"


def test_failed_checks_fall_back_to_full_log(fake_gh, run_script):
    fake_gh.route(
        (["pr", "view", "statusCheckRollup"], ROLLUP),
        (["run", "view", "--job", "22", "--log-failed"], ""),
        (["run", "view", "--job", "22", "--log"], "container never started\n"),
    )
    r = run_script("fetch-failed-pr-checks.sh", "7", *REPO)
    assert "container never started" in r.stdout


def test_failed_checks_none(fake_gh, run_script):
    fake_gh.route((["pr", "view", "statusCheckRollup"], {"statusCheckRollup": []}))
    r = run_script("fetch-failed-pr-checks.sh", "7", *REPO)
    assert r.returncode == 0, r.stderr
    assert "_No failed checks._" in r.stdout


def test_failed_checks_rejects_bad_pr(run_script):
    assert run_script("fetch-failed-pr-checks.sh", "abc", *REPO).returncode == 2


# --------------------------------------------------------------------------- fetch-coderabbit-threads


def _thread(*, resolved: bool, login: str, body: str, path: str) -> dict:
    return {
        "id": f"T_{path}", "isResolved": resolved, "isOutdated": False, "path": path, "line": 10,
        "originalLine": 10,
        "comments": {
            "pageInfo": {"hasNextPage": False, "endCursor": None},
            "nodes": [{"author": {"login": login}, "body": body, "url": f"https://x/{path}", "createdAt": "t"}],
        },
    }


GRAPHQL = {"data": {"repository": {"pullRequest": {"reviewThreads": {
    "pageInfo": {"hasNextPage": False, "endCursor": None},
    "nodes": [
        _thread(resolved=False, login="coderabbitai", body="Fix this", path="src/a.py"),
        _thread(resolved=True, login="coderabbitai", body="Old news", path="src/b.py"),
        _thread(resolved=False, login="someone", body="Human note", path="src/c.py"),
    ],
}}}}}

REVIEW_BODY = (
    "Actionable comments posted: 1\n\n"
    "<details>\n<summary>⚠️ Outside diff range comments (1)</summary><blockquote>\n\n"
    "Outside finding text\n\n</blockquote></details>\n"
    "<details>\n<summary>🧹 Nitpick comments (1)</summary><blockquote>\n\nNit finding text\n\n"
    "</blockquote></details>\n\n🤖 Prompt for all review comments with AI agents\n\nprompt"
)
REVIEWS = [{"user": {"login": "coderabbitai[bot]"}, "body": REVIEW_BODY, "html_url": "https://x/review/1",
            "submitted_at": "t"}]


def test_coderabbit_threads_nitpicks_and_outside_diff(fake_gh, run_script):
    fake_gh.route((["graphql"], GRAPHQL), (["repos/o/r/pulls/7/reviews"], REVIEWS))
    r = run_script("fetch-coderabbit-threads.sh", "7", *REPO)
    assert r.returncode == 0, r.stderr
    assert "## Thread 1 — src/a.py:10" in r.stdout
    assert "> Fix this" in r.stdout
    assert "Old news" not in r.stdout
    assert "Human note" not in r.stdout
    assert "### Nitpick 1" in r.stdout
    assert "Nit finding text" in r.stdout
    assert "### Outside-diff 1" in r.stdout
    assert "Outside finding text" in r.stdout
    data = json.loads(_json_path(r.stdout).read_text())
    assert [t["path"] for t in data["threads"]] == ["src/a.py"]


def test_coderabbit_threads_all_authors(fake_gh, run_script):
    fake_gh.route((["graphql"], GRAPHQL), (["repos/o/r/pulls/7/reviews"], []))
    r = run_script("fetch-coderabbit-threads.sh", "7", *REPO, "--all-authors")
    assert "Human note" in r.stdout
    assert "Old news" not in r.stdout
    assert "_No nitpicks._" in r.stdout


# --------------------------------------------------------------------------- wait-for-reviews

CLEAR = {"statusCheckRollup": [{"__typename": "CheckRun", "name": "tests", "status": "COMPLETED"}]}
WITH_CR = {"statusCheckRollup": [
    {"__typename": "CheckRun", "name": "tests", "status": "COMPLETED"},
    {"__typename": "StatusContext", "context": "CodeRabbit", "state": "SUCCESS"},
]}


def _cr_routes(comment_body: str) -> tuple:
    return (
        (["pr", "view", "statusCheckRollup"], WITH_CR),
        (["pr", "view", "headRefOid"], {"headRefOid": "abc"}),
        (["repos/o/r/commits/abc"], {"commit": {"committer": {"date": "2026-01-01T00:00:00Z"}}}),
        (["repos/o/r/issues/7/comments"],
         [{"user": {"login": "coderabbitai[bot]"}, "updated_at": "2026-01-02T00:00:00Z", "body": comment_body}]),
    )


def test_wait_gate_clear_without_coderabbit(fake_gh, run_script):
    fake_gh.route((["pr", "view", "statusCheckRollup"], CLEAR))
    r = run_script("wait-for-reviews.sh", "7", *REPO)
    assert r.returncode == 0, r.stderr
    assert "Stage 0a: gate clear." in r.stdout
    assert "no CodeRabbit StatusContext" in r.stdout


def test_wait_skip_coderabbit(fake_gh, run_script):
    fake_gh.route(*_cr_routes("## Summary"))
    r = run_script("wait-for-reviews.sh", "7", *REPO, "--skip-coderabbit")
    assert r.returncode == 0, r.stderr
    assert "CodeRabbit disabled" in r.stdout
    assert not any("repos/o/r/issues/7/comments" in c["argv"] for c in fake_gh.calls())


def test_wait_fresh_coderabbit_summary(fake_gh, run_script):
    fake_gh.route(*_cr_routes("## Summary"))
    r = run_script("wait-for-reviews.sh", "7", *REPO)
    assert r.returncode == 0, r.stderr
    assert "CodeRabbit summary updated" in r.stdout


def test_wait_detects_rate_limit(fake_gh, run_script):
    fake_gh.route(*_cr_routes("Review limit reached for this PR"))
    r = run_script("wait-for-reviews.sh", "7", *REPO)
    assert r.returncode == 3
    assert "RATE LIMITED" in r.stderr


def test_wait_gate_fails_closed_when_gh_errors(fake_gh, run_script, monkeypatch):
    fake_gh.route((["pr", "view", "statusCheckRollup"], "", 1))
    monkeypatch.setenv("LA_WAIT_GATE_TIMEOUT", "0")
    monkeypatch.setenv("LA_WAIT_POLL_SECONDS", "0")
    r = run_script("wait-for-reviews.sh", "7", *REPO)
    assert r.returncode == 1
    assert "gate clear" not in r.stdout
    assert "could not read the check rollup" in r.stdout


def test_wait_requires_pr(run_script):
    assert run_script("wait-for-reviews.sh").returncode == 64
