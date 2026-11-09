import json
import re
import subprocess
from pathlib import Path

import pytest

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


JOB_ONLY = {"statusCheckRollup": ROLLUP["statusCheckRollup"][:1]}
RUN_ONLY = {"statusCheckRollup": [{**ROLLUP["statusCheckRollup"][0],
                                   "detailsUrl": "https://github.com/o/r/actions/runs/11"}]}
LOG_FAILED = ["run", "view", "--job", "22", "--log-failed"]
FULL_LOG = ["run", "view", "--job", "22", "--log"]
API_LOGS = ["api", "repos/o/r/actions/jobs/22/logs"]
API_STEPS = ["api", "repos/o/r/actions/jobs/22"]
NO_RUN_VIEW_LOG = ((LOG_FAILED, ""), (FULL_LOG, ""))

# Three steps; step 2 is a composite action whose header shares its start second with step 1's last line,
# and whose completion second also holds the post step's first lines.
API_LOG_LINES = [
    "2026-01-01T00:00:01.0000000Z ##[group]Run actions/checkout@v4",
    "2026-01-01T00:00:02.0000000Z Syncing repository: o/r",
    "2026-01-01T00:00:09.0000000Z ##[endgroup]",
    "2026-01-01T00:00:10.1000000Z Checked out ref main",
    "2026-01-01T00:00:10.5000000Z ##[group]Run ./.github/actions/test",
    "2026-01-01T00:00:10.6000000Z ##[endgroup]",
    "2026-01-01T00:00:11.0000000Z ##[group]Run pnpm exec vitest run",
    "2026-01-01T00:00:11.1000000Z shell: /usr/bin/bash --noprofile --norc -e -o pipefail {0}",
    "2026-01-01T00:00:11.2000000Z ##[endgroup]",
    "2026-01-01T00:00:15.0000000Z FAIL src/a.test.ts > adds",
    "2026-01-01T00:00:19.0000000Z ##[error]AssertionError: expected 1 to be 2",
    "- Expected",
    "+ Received",
    "2026-01-01T00:00:20.0000000Z ##[error]Process completed with exit code 1.",
    "2026-01-01T00:00:20.1000000Z Post job cleanup.",
    "2026-01-01T00:00:20.2000000Z [command]/usr/bin/git version",
    "2026-01-01T00:00:21.0000000Z Cleaning up orphan processes",
]
API_LOG = "\n".join(API_LOG_LINES) + "\n"
STEP_2 = API_LOG_LINES[4:14]


def _step(number: int, conclusion: str | None, start: str | None, end: str | None) -> dict:
    return {"number": number, "name": f"step {number}", "conclusion": conclusion,
            "started_at": start and f"2026-01-01T{start}Z", "completed_at": end and f"2026-01-01T{end}Z"}


STEPS = {"steps": [_step(1, "success", "00:00:01", "00:00:10"), _step(2, "failure", "00:00:10", "00:00:20"),
                   _step(3, "success", "00:00:20", "00:00:21")]}
ALL_PASSED = {"steps": [_step(1, "success", "00:00:01", "00:00:21")]}


def _excerpt(*lines: str) -> str:
    return "\n".join(lines) + "\n"


def _attempt(command: str, outcome: str = "ok") -> dict:
    return {"command": command, "outcome": outcome}


EMPTY_RUN_VIEW_ATTEMPTS = [_attempt("gh run view --job 22 --log-failed", "empty log"),
                           _attempt("gh run view --job 22 --log", "empty log")]
RUN_VIEW_CALLS = ["run view --job 22 --log-failed", "run view --job 22 --log"]
API_CALLS = [*RUN_VIEW_CALLS, "api repos/o/r/actions/jobs/22/logs", "api repos/o/r/actions/jobs/22"]


def _fetch(fake_gh, run_script, rollup, *routes, max_log: str | None = None) -> tuple[str, list[dict]]:
    """Run the script; returns its Markdown and the JSON's failed checks."""
    fake_gh.route((["pr", "view", "statusCheckRollup"], rollup), *routes)
    r = run_script("fetch-failed-pr-checks.sh", "7", *REPO, *(["--max-log-lines", max_log] if max_log else []))
    assert r.returncode == 0, r.stderr
    assert r.stderr == ""
    return r.stdout, json.loads(_json_path(r.stdout).read_text())["failed_checks"]


def _log_calls(fake_gh) -> list[str]:
    """Every log-related gh call: `run view …` without `--repo o/r` (asserted present), or `api <endpoint>`."""
    out = []
    for call in fake_gh.calls():
        argv = call["argv"]
        if argv[:2] == ["run", "view"]:
            assert argv[argv.index("--repo") + 1] == "o/r"
            out.append(" ".join(t for t in argv if t not in ("--repo", "o/r")))
        elif argv[0] == "api":
            [endpoint] = [t for t in argv if t.startswith("repos/")]
            out.append(f"api {endpoint}")
    return out


def test_failed_checks_with_logs(fake_gh, run_script):
    out, checks = _fetch(fake_gh, run_script, ROLLUP, (LOG_FAILED, "step: boom\n"))
    assert "## Check 1 — CI / tests" in out
    assert "<details><summary>Failed-step log (last 200 lines)</summary>\n\n```\nstep: boom\n" in out
    assert "## Check 2 — ext-ci" in out
    assert "_No log excerpt available — likely an external CI; follow Details URL._" in out
    assert "lint" not in out
    assert [c["name"] for c in checks] == ["tests", "ext-ci"]
    assert checks[0]["job_id"] == "22"
    assert checks[0]["log_source"] == "log-failed"
    assert checks[0]["log_attempts"] == [_attempt("gh run view --job 22 --log-failed")]
    assert checks[1]["log_source"] is None
    assert checks[1]["log_attempts"] == []
    assert _log_calls(fake_gh) == RUN_VIEW_CALLS[:1]


def test_failed_checks_fall_back_to_full_log(fake_gh, run_script):
    out, [check] = _fetch(fake_gh, run_script, JOB_ONLY, (LOG_FAILED, ""), (FULL_LOG, "container never started\n"),
                          max_log="5")
    assert "<details><summary>Full log (last 5 lines)</summary>\n\n```\ncontainer never started\n" in out
    assert check["log_source"] == "log"
    assert check["log_attempts"] == [_attempt("gh run view --job 22 --log-failed", "empty log"),
                                     _attempt("gh run view --job 22 --log")]
    assert _log_calls(fake_gh) == RUN_VIEW_CALLS


@pytest.mark.parametrize("empty_first", [False, True])
def test_failed_checks_run_view_log_keeps_its_last_lines(fake_gh, run_script, empty_first):
    log = _excerpt("one", "two", "three", "four")
    routes = ((LOG_FAILED, ""), (FULL_LOG, log)) if empty_first else ((LOG_FAILED, log),)
    _, [check] = _fetch(fake_gh, run_script, JOB_ONLY, *routes, max_log="2")
    assert check["log_excerpt"] == _excerpt("three", "four")
    assert _log_calls(fake_gh) == RUN_VIEW_CALLS[: len(routes)]


def test_failed_checks_whitespace_only_log_falls_through(fake_gh, run_script):
    _, [check] = _fetch(fake_gh, run_script, JOB_ONLY, (LOG_FAILED, "\n  \n"), (FULL_LOG, "boom\n"))
    assert check["log_excerpt"] == "boom\n"
    assert check["log_source"] == "log"
    assert check["log_attempts"][0] == _attempt("gh run view --job 22 --log-failed", "empty log")
    assert _log_calls(fake_gh) == RUN_VIEW_CALLS


def test_failed_checks_nonzero_run_view_with_output_gives_the_excerpt(fake_gh, run_script):
    _, [check] = _fetch(fake_gh, run_script, JOB_ONLY, (LOG_FAILED, "step: boom\n", 1, "warning: partial\n"))
    assert check["log_excerpt"] == "step: boom\n"
    assert check["log_source"] == "log-failed"
    assert check["log_attempts"] == [_attempt("gh run view --job 22 --log-failed")]
    assert _log_calls(fake_gh) == RUN_VIEW_CALLS[:1]


def test_failed_checks_api_step(fake_gh, run_script):
    out, [check] = _fetch(fake_gh, run_script, JOB_ONLY, *NO_RUN_VIEW_LOG, (API_LOGS, API_LOG), (API_STEPS, STEPS))
    assert check["log_excerpt"] == _excerpt(*STEP_2)
    assert check["log_source"] == "api-step"
    assert check["log_attempts"] == [*EMPTY_RUN_VIEW_ATTEMPTS, _attempt("gh api repos/o/r/actions/jobs/22/logs"),
                                     _attempt("gh api repos/o/r/actions/jobs/22")]
    assert "<details><summary>Failed-step log from the job-log API (##[error] lines + last 200 lines)</summary>" in out
    assert _log_calls(fake_gh) == API_CALLS


def test_failed_checks_api_step_longer_than_max_keeps_earlier_errors(fake_gh, run_script):
    out, [check] = _fetch(fake_gh, run_script, JOB_ONLY, *NO_RUN_VIEW_LOG, (API_LOGS, API_LOG), (API_STEPS, STEPS),
                          max_log="3")
    assert check["log_excerpt"] == _excerpt("[... 6 lines omitted ...]", *STEP_2[6:])
    assert check["log_source"] == "api-step"
    assert "<details><summary>Failed-step log from the job-log API (##[error] lines + last 3 lines)</summary>" in out
    assert _log_calls(fake_gh) == API_CALLS


def test_failed_checks_api_step_header_in_start_second(fake_gh, run_script):
    log = _excerpt("2026-01-01T00:00:09.0000000Z previous step",
                   "2026-01-01T00:00:10.0000000Z previous step, last line",
                   "2026-01-01T00:00:10.0000000Z ##[group]Run make test",
                   "2026-01-01T00:00:11.0000000Z ##[error]Process completed with exit code 2.")
    steps = {"steps": [_step(1, "success", "00:00:09", "00:00:10"), _step(2, "failure", "00:00:10", "00:00:11")]}
    _, [check] = _fetch(fake_gh, run_script, JOB_ONLY, *NO_RUN_VIEW_LOG, (API_LOGS, log), (API_STEPS, steps))
    assert check["log_excerpt"] == _excerpt(*log.splitlines()[2:])
    assert check["log_source"] == "api-step"
    assert _log_calls(fake_gh) == API_CALLS


def test_failed_checks_api_cancelled_step_is_the_failed_step(fake_gh, run_script):
    steps = {"steps": [_step(1, "success", "00:00:01", "00:00:10"), _step(2, "skipped", None, None),
                       _step(3, "neutral", "00:00:10", "00:00:10"), _step(4, None, None, None),
                       _step(5, "cancelled", "00:00:10", "00:00:20"), _step(6, "success", "00:00:20", "00:00:21")]}
    _, [check] = _fetch(fake_gh, run_script, JOB_ONLY, *NO_RUN_VIEW_LOG, (API_LOGS, API_LOG), (API_STEPS, steps))
    assert check["log_excerpt"] == _excerpt(*STEP_2)
    assert check["log_source"] == "api-step"
    assert _log_calls(fake_gh) == API_CALLS


def test_failed_checks_api_no_failed_step(fake_gh, run_script):
    _, [check] = _fetch(fake_gh, run_script, JOB_ONLY, *NO_RUN_VIEW_LOG, (API_LOGS, API_LOG),
                        (API_STEPS, ALL_PASSED), max_log="3")
    assert check["log_excerpt"] == _excerpt("[... 10 lines omitted ...]", API_LOG_LINES[10],
                                            "[... 2 lines omitted ...]", *API_LOG_LINES[13:])
    assert check["log_source"] == "api-errors-tail"
    assert check["log_attempts"][-1] == _attempt("gh api repos/o/r/actions/jobs/22", "no failed step")
    assert _log_calls(fake_gh) == API_CALLS


def test_failed_checks_api_failed_step_outside_the_log(fake_gh, run_script):
    steps = {"steps": [_step(1, "failure", "00:05:00", "00:05:10")]}
    _, [check] = _fetch(fake_gh, run_script, JOB_ONLY, *NO_RUN_VIEW_LOG, (API_LOGS, API_LOG), (API_STEPS, steps))
    assert check["log_excerpt"] == API_LOG
    assert check["log_source"] == "api-errors-tail"
    assert check["log_attempts"][-1] == _attempt("gh api repos/o/r/actions/jobs/22",
                                                 "no log lines in the step's time window")
    assert _log_calls(fake_gh) == API_CALLS


def test_failed_checks_api_error_lines_at_line_start_or_after_a_space(fake_gh, run_script):
    log = _excerpt("2026-01-01T00:00:01.0000000Z start", "2026-01-01T00:00:02.0000000Z setup",
                   "##[error]raw annotation", "2026-01-01T00:00:03.0000000Z noise##[error]not an annotation",
                   "2026-01-01T00:00:04.0000000Z one", "2026-01-01T00:00:05.0000000Z two",
                   "2026-01-01T00:00:06.0000000Z three", "2026-01-01T00:00:07.0000000Z four")
    _, [check] = _fetch(fake_gh, run_script, JOB_ONLY, *NO_RUN_VIEW_LOG, (API_LOGS, log), (API_STEPS, ALL_PASSED),
                        max_log="2")
    lines = log.splitlines()
    assert check["log_excerpt"] == _excerpt("[... 2 lines omitted ...]", lines[2], "[... 3 lines omitted ...]",
                                            *lines[6:])
    assert _log_calls(fake_gh) == API_CALLS


def test_failed_checks_api_log_drops_the_bom(fake_gh, run_script):
    _, [check] = _fetch(fake_gh, run_script, JOB_ONLY, *NO_RUN_VIEW_LOG, (API_LOGS, "\ufeff" + API_LOG),
                        (API_STEPS, ALL_PASSED))
    assert check["log_excerpt"] == API_LOG
    assert _log_calls(fake_gh) == API_CALLS


@pytest.mark.parametrize(("exit_code", "stderr", "reason"), [
    (1, "warning: retrying\ngh: Server Error (HTTP 500)\n\n", "gh: Server Error (HTTP 500)"),
    (4, "", "exit 4"),
])
def test_failed_checks_api_metadata_failure_reason(fake_gh, run_script, exit_code, stderr, reason):
    _, [check] = _fetch(fake_gh, run_script, JOB_ONLY, *NO_RUN_VIEW_LOG, (API_LOGS, API_LOG),
                        (API_STEPS, "", exit_code, stderr))
    assert check["log_excerpt"] == API_LOG
    assert check["log_source"] == "api-errors-tail"
    assert check["log_attempts"][-1] == _attempt("gh api repos/o/r/actions/jobs/22", reason)
    assert _log_calls(fake_gh) == API_CALLS


def test_failed_checks_every_attempt_failed(fake_gh, run_script):
    out, [check] = _fetch(fake_gh, run_script, JOB_ONLY, (LOG_FAILED, "", 1, "HTTP 502\n"), (FULL_LOG, ""),
                          (API_LOGS, "", 1, "gh: Not Found (HTTP 404)\n"))
    assert check["log_excerpt"] == ""
    assert check["log_source"] is None
    assert check["log_attempts"] == [_attempt("gh run view --job 22 --log-failed", "HTTP 502"),
                                     _attempt("gh run view --job 22 --log", "empty log"),
                                     _attempt("gh api repos/o/r/actions/jobs/22/logs", "gh: Not Found (HTTP 404)")]
    assert ("_No log excerpt — every attempt failed:_\n"
            "- `gh run view --job 22 --log-failed`: HTTP 502\n"
            "- `gh run view --job 22 --log`: empty log\n"
            "- `gh api repos/o/r/actions/jobs/22/logs`: gh: Not Found (HTTP 404)\n") in out
    assert "likely an external CI" not in out
    assert _log_calls(fake_gh) == API_CALLS[:3]


def test_failed_checks_run_only_makes_no_api_call(fake_gh, run_script):
    out, [check] = _fetch(fake_gh, run_script, RUN_ONLY, (["run", "view", "11", "--log-failed"], ""),
                          (["run", "view", "11", "--log"], ""))
    assert check["log_attempts"] == [_attempt("gh run view 11 --log-failed", "empty log"),
                                     _attempt("gh run view 11 --log", "empty log")]
    assert ("_No log excerpt — every attempt failed:_\n"
            "- `gh run view 11 --log-failed`: empty log\n"
            "- `gh run view 11 --log`: empty log\n") in out
    assert _log_calls(fake_gh) == ["run view 11 --log-failed", "run view 11 --log"]


def test_failed_checks_max_log_zero_fetches_nothing(fake_gh, run_script):
    out, [check] = _fetch(fake_gh, run_script, JOB_ONLY, max_log="0")
    assert "_No log excerpt: log fetching is off (--max-log-lines 0)._" in out
    assert "likely an external CI" not in out
    assert check["log_source"] is None
    assert check["log_attempts"] == []
    assert _log_calls(fake_gh) == []


def test_failed_checks_leave_only_the_json_in_tmpdir(fake_gh, run_script):
    out, _ = _fetch(fake_gh, run_script, JOB_ONLY, *NO_RUN_VIEW_LOG, (API_LOGS, API_LOG), (API_STEPS, STEPS))
    left = {p.name for p in fake_gh.tmp.iterdir()} - {"fakebin", "routes.json", "gh.log"}
    assert left == {_json_path(out).name}


def test_failed_checks_usage_names_the_error_lines(run_script):
    r = run_script("fetch-failed-pr-checks.sh", "-h")
    assert r.returncode == 2
    assert ("--max-log-lines N    tail each failed job's log excerpt at N lines (default: 200); "
            "a job-log API excerpt also keeps the earlier ##[error] lines") in r.stderr


def test_failed_checks_with_a_log_larger_than_an_argument(fake_gh, run_script):
    log = "".join(f"line {n} {'x' * 200}\n" for n in range(1000))
    fake_gh.route(
        (["pr", "view", "statusCheckRollup"], ROLLUP),
        (["run", "view", "--job", "22", "--log-failed"], log),
    )
    r = run_script("fetch-failed-pr-checks.sh", "7", *REPO, "--max-log-lines", "1000")
    assert r.returncode == 0, r.stderr
    assert "line 999" in json.loads(_json_path(r.stdout).read_text())["failed_checks"][0]["log_excerpt"]


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


def test_coderabbit_threads_with_a_body_larger_than_an_argument(fake_gh, run_script):
    body = "big " * 50_000
    graphql = {"data": {"repository": {"pullRequest": {"reviewThreads": {
        "pageInfo": {"hasNextPage": False, "endCursor": None},
        "nodes": [_thread(resolved=False, login="coderabbitai", body=body, path="src/a.py")],
    }}}}}
    fake_gh.route((["graphql"], graphql), (["repos/o/r/pulls/7/reviews"], []))
    r = run_script("fetch-coderabbit-threads.sh", "7", *REPO)
    assert r.returncode == 0, r.stderr
    assert json.loads(_json_path(r.stdout).read_text())["threads"][0]["comments"]["nodes"][0]["body"] == body


def test_coderabbit_threads_all_authors(fake_gh, run_script):
    fake_gh.route((["graphql"], GRAPHQL), (["repos/o/r/pulls/7/reviews"], []))
    r = run_script("fetch-coderabbit-threads.sh", "7", *REPO, "--all-authors")
    assert "Human note" in r.stdout
    assert "Old news" not in r.stdout
    assert "_No nitpicks._" in r.stdout


# --------------------------------------------------------------------------- wait-for-reviews

CLEAR = {"statusCheckRollup": [{"__typename": "CheckRun", "name": "tests", "status": "COMPLETED"}]}
HUMAN_COMMENTS = [{"user": {"login": "alice"}, "updated_at": "2026-01-02T00:00:00Z", "body": "LGTM"}]
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
    fake_gh.route((["pr", "view", "statusCheckRollup"], CLEAR), (["repos/o/r/issues/7/comments"], HUMAN_COMMENTS))
    r = run_script("wait-for-reviews.sh", "7", *REPO)
    assert r.returncode == 0, r.stderr
    assert r.stdout == "Stage 0a: gate clear.\nStage 0b: CodeRabbit is not on this PR — skipping settle.\n"


def test_wait_settles_when_coderabbit_only_commented(fake_gh, run_script):
    fake_gh.route((["pr", "view", "statusCheckRollup"], CLEAR), *_cr_routes("## Summary")[1:])
    r = run_script("wait-for-reviews.sh", "7", *REPO)
    assert r.returncode == 0, r.stderr
    assert "CodeRabbit summary updated" in r.stdout


def test_wait_rejects_skip_coderabbit(fake_gh, run_script, monkeypatch):
    monkeypatch.setenv("LA_WAIT_GATE_TIMEOUT", "0")
    monkeypatch.setenv("LA_WAIT_POLL_SECONDS", "0")
    r = run_script("wait-for-reviews.sh", "7", *REPO, "--skip-coderabbit")
    assert r.returncode == 64
    assert "unknown flag: --skip-coderabbit" in r.stderr
    assert "--skip-coderabbit     " not in r.stderr
    assert fake_gh.calls() == []


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


# --------------------------------------------------------------------------- pr-reviewers

SONAR_RUN = {"__typename": "CheckRun", "name": "SonarCloud Code Analysis", "status": "COMPLETED",
             "detailsUrl": "https://sonarcloud.io/dashboard?id=url_key&pullRequest=7"}


@pytest.fixture
def git_repo(fake_gh):
    subprocess.run(["git", "init", "-q", str(fake_gh.tmp)], check=True)


def _reviewers(fake_gh, run_script, rollup, comments):
    fake_gh.route((["pr", "view", "statusCheckRollup"], {"statusCheckRollup": rollup}),
                  (["repos/o/r/issues/7/comments"], comments))
    r = run_script("pr-reviewers.sh", "7", *REPO)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


@pytest.mark.usefixtures("git_repo")
def test_pr_reviewers_coderabbit_by_status(fake_gh, run_script):
    rollup = WITH_CR["statusCheckRollup"]
    assert _reviewers(fake_gh, run_script, rollup, HUMAN_COMMENTS)["coderabbit"] is True


@pytest.mark.usefixtures("git_repo")
def test_pr_reviewers_coderabbit_by_comment(fake_gh, run_script):
    comments = [{"user": {"login": "coderabbitai[bot]"}, "updated_at": "t", "body": "## Summary"}]
    assert _reviewers(fake_gh, run_script, CLEAR["statusCheckRollup"], comments)["coderabbit"] is True


@pytest.mark.usefixtures("git_repo")
def test_pr_reviewers_no_bots(fake_gh, run_script):
    out = _reviewers(fake_gh, run_script, CLEAR["statusCheckRollup"], HUMAN_COMMENTS)
    assert out == {"coderabbit": False, "sonar": {"present": False, "project_key": None}}


@pytest.mark.usefixtures("git_repo")
def test_pr_reviewers_sonar_key_from_url(fake_gh, run_script):
    out = _reviewers(fake_gh, run_script, [*CLEAR["statusCheckRollup"], SONAR_RUN], [])
    assert out["sonar"] == {"present": True, "project_key": "url_key"}


@pytest.mark.usefixtures("git_repo")
def test_pr_reviewers_sonar_key_from_properties(fake_gh, run_script):
    (fake_gh.tmp / "sonar-project.properties").write_text("sonar.projectKey = props_key\n", encoding="utf-8")
    out = _reviewers(fake_gh, run_script, [*CLEAR["statusCheckRollup"], SONAR_RUN], [])
    assert out["sonar"] == {"present": True, "project_key": "props_key"}


@pytest.mark.usefixtures("git_repo")
def test_pr_reviewers_sonar_context_matched_case_insensitively(fake_gh, run_script):
    context = {"__typename": "StatusContext", "context": "SONARQUBE", "state": "SUCCESS", "targetUrl": "https://s/x"}
    out = _reviewers(fake_gh, run_script, [*CLEAR["statusCheckRollup"], context], [])
    assert out["sonar"] == {"present": True, "project_key": None}


@pytest.mark.usefixtures("git_repo")
def test_pr_reviewers_gh_failure(fake_gh, run_script):
    fake_gh.route((["pr", "view", "statusCheckRollup"], "", 1))
    r = run_script("pr-reviewers.sh", "7", *REPO)
    assert r.returncode == 2
    assert r.stdout == ""


@pytest.mark.parametrize("args", [[], ["abc", *REPO], ["-3", *REPO]])
def test_pr_reviewers_rejects_missing_or_bad_pr(fake_gh, run_script, args):
    r = run_script("pr-reviewers.sh", *args)
    assert r.returncode == 2
    assert r.stdout == ""
    assert fake_gh.calls() == []
