import json
import re
import subprocess
from pathlib import Path
from typing import Any

import pytest

from living_architecture.config import current_format

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
    left = {p.name for p in fake_gh.tmp.iterdir()} - {"fakebin", "routes.json", "routes.json.counts", "gh.log"}
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


# --------------------------------------------------------------------------- fake gh


def test_fake_gh_serves_sequenced_responses(fake_gh):
    fake_gh.route({"match": ["x"], "responses": [{"stdout": "one"}, {"stdout": "", "exit": 4}, {"stdout": "three"}]},
                  (["y"], "always"))

    def gh(arg: str) -> tuple[str, int]:
        r = subprocess.run([str(fake_gh.bin / "gh"), arg], env=fake_gh.env(), capture_output=True, text=True,
                           check=False)
        return r.stdout, r.returncode

    assert [gh(a) for a in ("x", "y", "x", "x", "x")] == [("one", 0), ("always", 0), ("", 4), ("three", 0), ("three", 0)]


# --------------------------------------------------------------------------- wait-for-reviews

HEAD = "abc"
SNAPSHOT = ["pr", "view", "headRefOid,statusCheckRollup"]
TESTS_RUN = {"__typename": "CheckRun", "name": "tests", "status": "COMPLETED"}
CR_CONTEXT = {"__typename": "StatusContext", "context": "CodeRabbit", "state": "SUCCESS"}
SONAR_RUN = {"__typename": "CheckRun", "name": "SonarCloud Code Analysis", "status": "COMPLETED",
             "detailsUrl": "https://sonarcloud.io/dashboard?id=url_key&pullRequest=7"}
CR_USER = {"login": "coderabbitai[bot]"}
HUMAN_COMMENTS = [{"user": {"login": "alice"}, "updated_at": "2026-01-02T00:00:00Z", "body": "LGTM"}]
SUMMARIZE = "<!-- This is an auto-generated comment: summarize by coderabbit.ai -->"
CR_REVIEW = "<!-- coderabbit-ai-generated:v1 -->\n**Actionable comments posted: 1**"

CLEARED = "Stage 0a: gate clear.\n"
CAP = "Stage 0b: hit 0m cap without CodeRabbit evidence for HEAD abc — proceeding anyway.\n"
RATE_LIMITED = "Stage 0b: CodeRabbit is RATE LIMITED — no review ran for HEAD abc.\n"
PAUSED = "Stage 0b: CodeRabbit reviews are PAUSED — no review ran for HEAD abc.\n"
RETRIGGER = ("Stage 0b: re-trigger with 'gh pr comment 7 --repo o/r --body \"@coderabbitai review\"' "
             "once the window clears.\n")


def _reviewed(evidence: str, head: str = HEAD) -> str:
    return f"Stage 0b: CodeRabbit reviewed HEAD {head} ({evidence}).\n"


def _coverage(sha: str) -> str:
    return f'<!-- final_review_risk_coverage:{{"sourceCommitId":"{sha}","coveredCommitId":"{sha}","kind":"reviewed"}} -->'


def _summary(text: str = "## Summary", *, covers: str | None = None) -> dict:
    body = "\n".join([SUMMARIZE, text, *([_coverage(covers)] if covers else [])])
    return {"user": CR_USER, "updated_at": "2026-01-02T00:00:00Z", "body": body}


def _cr_reply(body: str) -> dict:
    return {"user": CR_USER, "updated_at": "2026-01-03T00:00:00Z", "body": body}


def _status(description: str, state: str = "success", context: str = "CodeRabbit") -> dict:
    return {"context": context, "state": state, "description": description}


def _review(body: str = CR_REVIEW, *, commit: str = HEAD, login: str = "coderabbitai[bot]") -> dict:
    return {"user": {"login": login}, "commit_id": commit, "body": body}


def _suite(slug: str, status: str) -> dict:
    return {"app": {"slug": slug}, "status": status}


def _routes(*, head: str = HEAD, rollup=(TESTS_RUN, CR_CONTEXT), suites=(), comments=(), statuses=(),
            reviews=()) -> dict[str, Any]:
    """The wait's reads by name: the HEAD snapshot, HEAD's check suites, comments, HEAD's statuses, reviews."""
    return {
        "snapshot": (SNAPSHOT, {"headRefOid": head, "statusCheckRollup": list(rollup)}),
        "suites": ([f"repos/o/r/commits/{head}/check-suites"], {"check_suites": list(suites)}),
        "comments": (["repos/o/r/issues/7/comments"], list(comments)),
        "statuses": ([f"repos/o/r/commits/{head}/statuses"], list(statuses)),
        "reviews": (["repos/o/r/pulls/7/reviews"], list(reviews)),
    }


@pytest.fixture
def fast_wait(monkeypatch):
    for name in ("LA_WAIT_GATE_TIMEOUT", "LA_WAIT_POLL_SECONDS", "LA_WAIT_CR_SETTLE"):
        monkeypatch.setenv(name, "0")


def _wait(fake_gh, run_script, routes: dict) -> subprocess.CompletedProcess[str]:
    fake_gh.route(*routes.values())
    return run_script("wait-for-reviews.sh", "7", *REPO)


@pytest.mark.usefixtures("fast_wait")
def test_wait_gate_clear_without_coderabbit(fake_gh, run_script):
    r = _wait(fake_gh, run_script, _routes(rollup=[TESTS_RUN], comments=HUMAN_COMMENTS))
    assert r.returncode == 0, r.stderr
    assert r.stdout == CLEARED + "Stage 0b: CodeRabbit is not on this PR — skipping settle.\n"


@pytest.mark.usefixtures("fast_wait")
def test_wait_settles_when_coderabbit_only_commented(fake_gh, run_script):
    r = _wait(fake_gh, run_script, _routes(rollup=[TESTS_RUN], comments=[_summary(covers=HEAD)]))
    assert r.returncode == 0, r.stderr
    assert r.stdout == CLEARED + _reviewed("summary covers HEAD")


def test_wait_rejects_skip_coderabbit(fake_gh, run_script, monkeypatch):
    monkeypatch.setenv("LA_WAIT_GATE_TIMEOUT", "0")
    monkeypatch.setenv("LA_WAIT_POLL_SECONDS", "0")
    r = run_script("wait-for-reviews.sh", "7", *REPO, "--skip-coderabbit")
    assert r.returncode == 64
    assert "unknown flag: --skip-coderabbit" in r.stderr
    assert "--skip-coderabbit     " not in r.stderr
    assert fake_gh.calls() == []


@pytest.mark.usefixtures("fast_wait")
def test_wait_gate_fails_closed_when_gh_errors(fake_gh, run_script):
    fake_gh.route((SNAPSHOT, "", 1))
    r = run_script("wait-for-reviews.sh", "7", *REPO)
    assert r.returncode == 1
    assert "gate clear" not in r.stdout
    assert "could not read the check rollup" in r.stdout


def test_wait_requires_pr(run_script):
    assert run_script("wait-for-reviews.sh").returncode == 64


# Stage 0a: Sonar check suites on HEAD


@pytest.mark.usefixtures("fast_wait")
@pytest.mark.parametrize(("slug", "status"), [("sonarqubecloud", "queued"), ("sonarqubecloud", "in_progress"),
                                              ("SonarCloud", "queued")])
def test_wait_gate_waits_for_pending_sonar_suite(fake_gh, run_script, slug, status):
    r = _wait(fake_gh, run_script, _routes(rollup=[TESTS_RUN], suites=[_suite(slug, status)]))
    assert r.returncode == 1
    assert "gate clear" not in r.stdout
    assert f"Stage 0a: pending — {slug} (check suite) (elapsed 0m). Sleeping 0s.\n" in r.stdout
    assert f"Still pending: {slug} (check suite)." in r.stderr


@pytest.mark.usefixtures("fast_wait")
def test_wait_gate_waits_for_sonar_suite_beside_completed_sonar_run(fake_gh, run_script):
    r = _wait(fake_gh, run_script, _routes(rollup=[TESTS_RUN, SONAR_RUN], suites=[_suite("sonarqubecloud", "queued")]))
    assert r.returncode == 1
    assert "gate clear" not in r.stdout
    assert "Still pending: sonarqubecloud (check suite)." in r.stderr


@pytest.mark.usefixtures("fast_wait")
def test_wait_gate_clears_on_completed_sonar_suite_beside_idle_apps(fake_gh, run_script):
    suites = [_suite("sonarqubecloud", "completed"), _suite("github-actions", "queued")]
    r = _wait(fake_gh, run_script, _routes(rollup=[TESTS_RUN], suites=suites, comments=HUMAN_COMMENTS))
    assert r.returncode == 0, r.stderr
    assert r.stdout == CLEARED + "Stage 0b: CodeRabbit is not on this PR — skipping settle.\n"


@pytest.mark.usefixtures("fast_wait")
@pytest.mark.parametrize("suites_route", [("", 1), ({"check_suites": ["{not json"]}, 0)], ids=["fails", "invalid"])
def test_wait_gate_stays_closed_when_suites_unreadable(fake_gh, run_script, suites_route):
    routes = _routes(rollup=[TESTS_RUN], comments=HUMAN_COMMENTS)
    routes["suites"] = (routes["suites"][0], *suites_route)
    r = _wait(fake_gh, run_script, routes)
    assert r.returncode == 1
    assert "gate clear" not in r.stdout
    assert [c for c in fake_gh.calls() if "repos/o/r/commits/abc/check-suites" in c["argv"]]


# Stage 0b: CodeRabbit evidence keyed to HEAD


@pytest.mark.usefixtures("fast_wait")
def test_wait_settles_when_summary_covers_head(fake_gh, run_script):
    r = _wait(fake_gh, run_script, _routes(comments=[_summary(covers=HEAD)]))
    assert (r.returncode, r.stdout, r.stderr) == (0, CLEARED + _reviewed("summary covers HEAD"), "")


@pytest.mark.usefixtures("fast_wait")
def test_wait_placeholder_summary_does_not_settle(fake_gh, run_script):
    r = _wait(fake_gh, run_script, _routes(comments=[_summary()]))
    assert (r.returncode, r.stdout, r.stderr) == (0, CLEARED, CAP)


@pytest.mark.usefixtures("fast_wait")
def test_wait_settles_on_completed_status_without_coverage(fake_gh, run_script):
    r = _wait(fake_gh, run_script, _routes(comments=[_summary(covers="prev")], statuses=[_status("Review completed")]))
    assert (r.returncode, r.stdout) == (0, CLEARED + _reviewed('status "Review completed"'))


@pytest.mark.usefixtures("fast_wait")
def test_wait_settles_on_review_on_head(fake_gh, run_script):
    r = _wait(fake_gh, run_script, _routes(comments=[_summary()], reviews=[_review()]))
    assert (r.returncode, r.stdout) == (0, CLEARED + _reviewed("review on HEAD"))


@pytest.mark.usefixtures("fast_wait")
@pytest.mark.parametrize("review", [_review(""), _review(commit="prev"), _review(login="alice")],
                         ids=["empty-body", "other-commit", "other-author"])
def test_wait_ignores_reviews_other_than_coderabbits_on_head(fake_gh, run_script, review):
    r = _wait(fake_gh, run_script, _routes(comments=[_summary()], reviews=[review]))
    assert (r.returncode, r.stdout, r.stderr) == (0, CLEARED, CAP)


@pytest.mark.usefixtures("fast_wait")
@pytest.mark.parametrize(("statuses", "reviews", "evidence"), [
    ([_status("Review completed")], [_review()], 'status "Review completed"'),
    ([], [_review()], "summary covers HEAD"),
], ids=["status-first", "summary-before-review"])
def test_wait_reports_the_first_evidence(fake_gh, run_script, statuses, reviews, evidence):
    r = _wait(fake_gh, run_script, _routes(comments=[_summary(covers=HEAD)], statuses=statuses, reviews=reviews))
    assert (r.returncode, r.stdout) == (0, CLEARED + _reviewed(evidence))


@pytest.mark.usefixtures("fast_wait")
def test_wait_matches_status_descriptions_case_insensitively(fake_gh, run_script):
    r = _wait(fake_gh, run_script, _routes(comments=[_summary()], statuses=[_status("review COMPLETED")]))
    assert (r.returncode, r.stdout) == (0, CLEARED + _reviewed('status "Review completed"'))


@pytest.mark.usefixtures("fast_wait")
def test_wait_ignores_statuses_of_other_contexts(fake_gh, run_script):
    statuses = [_status("Review rate limited", context="other-bot"), _status("Review completed", context="ci")]
    r = _wait(fake_gh, run_script, _routes(comments=[_summary()], statuses=statuses))
    assert (r.returncode, r.stdout, r.stderr) == (0, CLEARED, CAP)


@pytest.mark.usefixtures("fast_wait")
@pytest.mark.parametrize("comment", [
    _cr_reply(f"Sure, reviewing.\n{_coverage(HEAD)}"),
    {"user": {"login": "alice"}, "updated_at": "2026-01-03T00:00:00Z", "body": f"{SUMMARIZE}\n{_coverage(HEAD)}"},
], ids=["coderabbit-reply", "human-copy"])
def test_wait_summary_is_coderabbits_summarize_comment(fake_gh, run_script, comment):
    r = _wait(fake_gh, run_script, _routes(comments=[_summary(), comment]))
    assert (r.returncode, r.stdout, r.stderr) == (0, CLEARED, CAP)


@pytest.mark.usefixtures("fast_wait")
@pytest.mark.parametrize("statuses", [[_status("Review in progress", state="pending")], [_status("Something new")]],
                         ids=["in-progress", "unknown"])
def test_wait_other_statuses_poll_to_cap(fake_gh, run_script, statuses):
    r = _wait(fake_gh, run_script, _routes(comments=[_summary()], statuses=statuses))
    assert (r.returncode, r.stdout, r.stderr) == (0, CLEARED, CAP)


@pytest.mark.usefixtures("fast_wait")
def test_wait_detects_rate_limit(fake_gh, run_script):
    comments = [_summary("Review limit reached", covers="prev"), _cr_reply("@coderabbitai review — on it.")]
    r = _wait(fake_gh, run_script, _routes(comments=comments, statuses=[_status("Review rate limited")]))
    assert (r.returncode, r.stdout, r.stderr) == (3, CLEARED, RATE_LIMITED + RETRIGGER)


@pytest.mark.usefixtures("fast_wait")
def test_wait_detects_pause(fake_gh, run_script):
    r = _wait(fake_gh, run_script, _routes(comments=[_summary()], statuses=[_status("Review paused")]))
    assert (r.returncode, r.stdout, r.stderr) == (3, CLEARED, PAUSED + RETRIGGER)


@pytest.mark.usefixtures("fast_wait")
@pytest.mark.parametrize(("statuses", "message"), [
    ([_status("Review paused"), _status("Review rate limited")], PAUSED),
    ([_status("Review rate limited"), _status("Review paused")], RATE_LIMITED),
], ids=["paused-latest", "rate-limited-latest"])
def test_wait_latest_status_decides(fake_gh, run_script, statuses, message):
    r = _wait(fake_gh, run_script, _routes(comments=[_summary()], statuses=statuses))
    assert (r.returncode, r.stderr) == (3, message + RETRIGGER)


@pytest.mark.usefixtures("fast_wait")
def test_wait_carried_forward(fake_gh, run_script):
    r = _wait(fake_gh, run_script, _routes(comments=[_summary(covers="prev")],
                                           statuses=[_status("Prior review carried forward")]))
    assert (r.returncode, r.stdout, r.stderr) == (
        0, CLEARED + "Stage 0b: CodeRabbit carried its prior review forward to HEAD abc.\n", "")


@pytest.mark.usefixtures("fast_wait")
@pytest.mark.parametrize(("statuses", "comments", "evidence"), [
    ([_status("Review rate limited"), _status("Review completed")], [_summary()], 'status "Review completed"'),
    ([_status("Review paused")], [_summary(covers=HEAD)], "summary covers HEAD"),
    ([_status("Prior review carried forward")], [_summary(covers=HEAD)], "summary covers HEAD"),
], ids=["completed-then-rate-limited", "paused-but-covered", "carried-forward-but-covered"])
def test_wait_reviewed_wins(fake_gh, run_script, statuses, comments, evidence):
    r = _wait(fake_gh, run_script, _routes(comments=comments, statuses=statuses))
    assert (r.returncode, r.stdout, r.stderr) == (0, CLEARED + _reviewed(evidence), "")


@pytest.mark.usefixtures("fast_wait")
def test_wait_stale_rate_limit_text_with_fresh_reply(fake_gh, run_script):
    comments = [_summary("Review limit reached", covers="prev"), _cr_reply("Sure!")]
    r = _wait(fake_gh, run_script, _routes(comments=comments))
    assert (r.returncode, r.stdout, r.stderr) == (0, CLEARED, CAP)


@pytest.mark.usefixtures("fast_wait")
def test_wait_names_head_by_its_short_sha(fake_gh, run_script):
    head = "0123456789abcdef0123456789abcdef01234567"
    r = _wait(fake_gh, run_script, _routes(head=head, comments=[_summary(covers=head)]))
    assert (r.returncode, r.stdout) == (0, CLEARED + _reviewed("summary covers HEAD", "0123456"))


@pytest.mark.usefixtures("fast_wait")
def test_wait_reads_lists_paginated(fake_gh, run_script):
    r = _wait(fake_gh, run_script, _routes(rollup=[TESTS_RUN], comments=[_summary()]))
    assert r.returncode == 0, r.stderr
    suffixes = ("/comments", "/statuses", "/reviews", "/check-suites")
    lists = [c["argv"] for c in fake_gh.calls() if any(a.endswith(suffixes) for a in c["argv"])]
    assert {next(a for a in argv if a.endswith(suffixes)).rsplit("/", 1)[1] for argv in lists} == {
        s[1:] for s in suffixes}
    assert all("--paginate" in argv for argv in lists), lists
    jq = {argv[argv.index("--jq") + 1] for argv in lists if "--jq" in argv}
    assert [argv for argv in lists if "--jq" in argv] == lists
    assert jq == {".[]", ".check_suites[]"}


def _fail_after_first(route: tuple) -> dict:
    return {"match": route[0], "responses": [{"stdout": route[1]}, {"stdout": "", "exit": 1}]}


@pytest.mark.usefixtures("fast_wait")
@pytest.mark.parametrize("terminal", ["Review rate limited", "Review paused", "Prior review carried forward"])
@pytest.mark.parametrize("source", ["snapshot", "suites", "comments", "statuses", "reviews", "statuses-invalid"])
def test_wait_failed_read_is_never_an_answer(fake_gh, run_script, source, terminal):
    routes = _routes(comments=[_summary()], statuses=[_status(terminal)])
    if source in ("snapshot", "suites"):
        routes[source] = _fail_after_first(routes[source])
    elif source == "statuses-invalid":
        # jq -r prints the string raw, so the script reads the malformed line `{not json`.
        routes["statuses"] = (routes["statuses"][0], ["{not json"])
    else:
        routes[source] = (routes[source][0], "", 1)
    r = _wait(fake_gh, run_script, routes)
    assert r.returncode == 0, r.stderr
    assert "RATE LIMITED" not in r.stderr
    assert "PAUSED" not in r.stderr
    assert "carried" not in r.stdout
    assert "reviewed" not in r.stdout
    assert "hit 0m cap" in r.stderr


@pytest.mark.usefixtures("fast_wait")
@pytest.mark.parametrize(("failing", "comments", "statuses", "evidence"), [
    ("statuses", [_summary(covers=HEAD)], [], "summary covers HEAD"),
    ("reviews", [_summary()], [_status("Review completed")], 'status "Review completed"'),
    ("comments", [], [_status("Review completed")], 'status "Review completed"'),
])
def test_wait_reviewed_stands_on_the_reads_that_succeeded(fake_gh, run_script, failing, comments, statuses, evidence):
    routes = _routes(comments=comments, statuses=statuses)
    routes[failing] = (routes[failing][0], "", 1)
    r = _wait(fake_gh, run_script, routes)
    assert (r.returncode, r.stdout) == (0, CLEARED + _reviewed(evidence))


def test_wait_keeps_polling_after_a_failed_read(fake_gh, run_script, monkeypatch):
    monkeypatch.setenv("LA_WAIT_GATE_TIMEOUT", "0")
    monkeypatch.setenv("LA_WAIT_POLL_SECONDS", "0")
    routes = _routes(comments=[_summary()])
    routes["statuses"] = {"match": routes["statuses"][0],
                          "responses": [{"stdout": "", "exit": 1}, {"stdout": [_status("Review completed")]}]}
    r = _wait(fake_gh, run_script, routes)
    assert (r.returncode, r.stdout) == (0, CLEARED
                                        + "Stage 0b: waiting for CodeRabbit on HEAD abc (elapsed 0m). Sleeping 30s.\n"
                                        + _reviewed('status "Review completed"'))


@pytest.mark.usefixtures("fast_wait")
def test_wait_restarts_when_head_moves(fake_gh, run_script):
    abc, defs = _routes(statuses=[_status("Review completed")]), _routes(head="def", statuses=[_status("Review completed")])
    snapshots = [{"stdout": abc["snapshot"][1]}, {"stdout": defs["snapshot"][1]}]
    fake_gh.route({"match": SNAPSHOT, "responses": snapshots}, abc["suites"], defs["suites"], abc["statuses"],
                  defs["statuses"], (abc["comments"][0], [_summary()]), abc["reviews"])
    r = run_script("wait-for-reviews.sh", "7", *REPO)
    assert (r.returncode, r.stdout) == (0, CLEARED + "Stage 0b: HEAD moved from abc to def — restarting Stage 0a.\n"
                                        + CLEARED + _reviewed('status "Review completed"', "def"))
    assert [c for c in fake_gh.calls() if "repos/o/r/commits/def/check-suites" in c["argv"]]


# --------------------------------------------------------------------------- pr-reviewers


@pytest.fixture
def git_repo(fake_gh):
    subprocess.run(["git", "init", "-q", str(fake_gh.tmp)], check=True)


def _reviewers(fake_gh, run_script, rollup, comments, suites=()):
    routes = _routes(rollup=rollup, comments=comments, suites=suites)
    fake_gh.route(routes["snapshot"], routes["suites"], routes["comments"])
    r = run_script("pr-reviewers.sh", "7", *REPO)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


@pytest.mark.usefixtures("git_repo")
def test_pr_reviewers_coderabbit_by_status(fake_gh, run_script):
    assert _reviewers(fake_gh, run_script, [TESTS_RUN, CR_CONTEXT], HUMAN_COMMENTS)["coderabbit"] is True


@pytest.mark.usefixtures("git_repo")
def test_pr_reviewers_coderabbit_by_comment(fake_gh, run_script):
    comments = [{"user": CR_USER, "updated_at": "t", "body": "## Summary"}]
    assert _reviewers(fake_gh, run_script, [TESTS_RUN], comments)["coderabbit"] is True


@pytest.mark.usefixtures("git_repo")
def test_pr_reviewers_no_bots(fake_gh, run_script):
    out = _reviewers(fake_gh, run_script, [TESTS_RUN], HUMAN_COMMENTS, suites=[_suite("github-actions", "completed")])
    assert out == {"coderabbit": False, "sonar": {"present": False, "project_key": None}}


@pytest.mark.usefixtures("git_repo")
def test_pr_reviewers_sonar_key_from_url(fake_gh, run_script):
    out = _reviewers(fake_gh, run_script, [TESTS_RUN, SONAR_RUN], [])
    assert out["sonar"] == {"present": True, "project_key": "url_key"}


@pytest.mark.usefixtures("git_repo")
def test_pr_reviewers_sonar_key_from_properties(fake_gh, run_script):
    (fake_gh.tmp / "sonar-project.properties").write_text("sonar.projectKey = props_key\n", encoding="utf-8")
    out = _reviewers(fake_gh, run_script, [TESTS_RUN, SONAR_RUN], [])
    assert out["sonar"] == {"present": True, "project_key": "props_key"}


@pytest.mark.usefixtures("git_repo")
def test_pr_reviewers_sonar_context_matched_case_insensitively(fake_gh, run_script):
    context = {"__typename": "StatusContext", "context": "SONARQUBE", "state": "SUCCESS", "targetUrl": "https://s/x"}
    out = _reviewers(fake_gh, run_script, [TESTS_RUN, context], [])
    assert out["sonar"] == {"present": True, "project_key": None}


@pytest.mark.usefixtures("git_repo")
@pytest.mark.parametrize(("slug", "status"), [("sonarqubecloud", "queued"), ("SonarCloud", "completed")])
def test_pr_reviewers_sonar_by_check_suite_only(fake_gh, run_script, slug, status):
    (fake_gh.tmp / "living-architecture.yaml").write_text(
        f"format: {current_format()}\nreviewers: {{sonar: {{project_key: cfg_key}}}}\n", encoding="utf-8")
    out = _reviewers(fake_gh, run_script, [TESTS_RUN], [], suites=[_suite(slug, status)])
    assert out["sonar"] == {"present": True, "project_key": "cfg_key"}


@pytest.mark.usefixtures("git_repo")
def test_pr_reviewers_sonar_suite_without_key(fake_gh, run_script):
    out = _reviewers(fake_gh, run_script, [TESTS_RUN], [], suites=[_suite("sonarqubecloud", "queued")])
    assert out["sonar"] == {"present": True, "project_key": None}


@pytest.mark.usefixtures("git_repo")
def test_pr_reviewers_reads_no_suites_beside_a_sonar_check(fake_gh, run_script):
    _reviewers(fake_gh, run_script, [TESTS_RUN, SONAR_RUN], [])
    assert not [c for c in fake_gh.calls() if any("check-suites" in a for a in c["argv"])]


@pytest.mark.usefixtures("git_repo")
def test_pr_reviewers_suites_read_fails(fake_gh, run_script):
    routes = _routes(rollup=[TESTS_RUN], comments=[])
    fake_gh.route(routes["snapshot"], routes["comments"])
    r = run_script("pr-reviewers.sh", "7", *REPO)
    assert (r.returncode, r.stdout) == (2, "")
    assert "fake gh: no route for" in r.stderr
    assert [c for c in fake_gh.calls() if "repos/o/r/commits/abc/check-suites" in c["argv"]]


@pytest.mark.usefixtures("git_repo")
def test_pr_reviewers_gh_failure(fake_gh, run_script):
    fake_gh.route((SNAPSHOT, "", 1))
    r = run_script("pr-reviewers.sh", "7", *REPO)
    assert r.returncode == 2
    assert r.stdout == ""


@pytest.mark.parametrize("args", [[], ["abc", *REPO], ["-3", *REPO]])
def test_pr_reviewers_rejects_missing_or_bad_pr(fake_gh, run_script, args):
    r = run_script("pr-reviewers.sh", *args)
    assert r.returncode == 2
    assert r.stdout == ""
    assert fake_gh.calls() == []
