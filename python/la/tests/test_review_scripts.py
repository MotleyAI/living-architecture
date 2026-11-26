import json
import re
import subprocess
from pathlib import Path
from typing import Any

import pytest

from trmv.config import current_format

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


REVIEW_URL = "https://github.com/o/r/pull/5#pullrequestreview-1"
CONVERSATION_URL = "https://github.com/o/r/pull/5#issuecomment-9"


@pytest.mark.parametrize("url", [REVIEW_URL, CONVERSATION_URL], ids=["review-body", "conversation-comment"])
def test_reply_to_an_unthreaded_comment_posts_a_re_comment(fake_gh, run_script, url):
    fake_gh.route((["api", "POST"], {"html_url": "https://github.com/o/r/pull/5#issuecomment-77"}))
    r = run_script("reply-to-pr-thread.sh", url, stdin="Fixed in abc1234.\n")
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "https://github.com/o/r/pull/5#issuecomment-77"
    [call] = fake_gh.calls()
    assert "repos/o/r/issues/5/comments" in call["argv"]
    assert json.loads(call["input"]) == {"body": f"Re: {url}\n\nFixed in abc1234.\n"}


@pytest.mark.parametrize("url", ["https://github.com/o/r/pull/5#discussion_r1", REVIEW_URL, CONVERSATION_URL],
                         ids=["discussion", "review-body", "conversation-comment"])
def test_reply_rejects_empty_body(fake_gh, run_script, url):
    r = run_script("reply-to-pr-thread.sh", url, stdin="")
    assert r.returncode == 2
    assert fake_gh.calls() == []


def test_reply_usage_names_every_url_form(run_script):
    r = run_script("reply-to-pr-thread.sh", "-h")
    assert r.returncode == 2
    assert all(form in r.stderr for form in ("#discussion_r", "#pullrequestreview-", "#issuecomment-"))


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


JOB_2 = "https://github.com/o/r/actions/runs/1/job/2"
JOB_4 = "https://github.com/o/r/actions/runs/3/job/4"


def _check(fake_gh, run_script, rollup, check: str, *routes) -> tuple[str, list[dict]]:
    """Run the script with `--check`; returns its Markdown and the JSON's failed checks."""
    fake_gh.route((["pr", "view", "statusCheckRollup"], rollup), *routes)
    r = run_script("fetch-failed-pr-checks.sh", "7", *REPO, "--check", check)
    assert r.returncode == 0, r.stderr
    return r.stdout, json.loads(_json_path(r.stdout).read_text())["failed_checks"]


def test_failed_checks_check_by_details_url_fetches_only_its_log(fake_gh, run_script):
    tests = ROLLUP["statusCheckRollup"][0]
    rollup = {"statusCheckRollup": [{**tests, "detailsUrl": JOB_2}, {**tests, "detailsUrl": JOB_4}]}
    out, checks = _check(fake_gh, run_script, rollup, JOB_4, (["run", "view", "--job", "4", "--log-failed"], "boom\n"))
    assert [c["details_url"] for c in checks] == [JOB_4]
    assert JOB_2 not in out
    assert _log_calls(fake_gh) == ["run view --job 4 --log-failed"]


def test_failed_checks_check_by_name(fake_gh, run_script):
    rollup = {"statusCheckRollup": [ROLLUP["statusCheckRollup"][0],
                                    {"__typename": "StatusContext", "context": "ext-ci", "state": "ERROR"}]}
    _, checks = _check(fake_gh, run_script, rollup, "ext-ci")
    assert [c["name"] for c in checks] == ["ext-ci"]
    assert _log_calls(fake_gh) == []


def test_failed_checks_check_by_name_keeps_every_match(fake_gh, run_script):
    tests = ROLLUP["statusCheckRollup"][0]
    rollup = {"statusCheckRollup": [{**tests, "detailsUrl": JOB_2}, {**tests, "detailsUrl": JOB_4}]}
    _, checks = _check(fake_gh, run_script, rollup, "tests", (["run", "view", "--job", "2", "--log-failed"], "a\n"),
                       (["run", "view", "--job", "4", "--log-failed"], "b\n"))
    assert [c["details_url"] for c in checks] == [JOB_2, JOB_4]
    assert _log_calls(fake_gh) == ["run view --job 2 --log-failed", "run view --job 4 --log-failed"]


def test_failed_checks_check_without_match_lists_none(fake_gh, run_script):
    out, checks = _check(fake_gh, run_script, ROLLUP, "other")
    assert "_No failed checks._" in out
    assert checks == []
    assert _log_calls(fake_gh) == []


def test_failed_checks_check_requires_a_value(fake_gh, run_script):
    assert run_script("fetch-failed-pr-checks.sh", "7", *REPO, "--check").returncode == 2
    assert fake_gh.calls() == []


# --------------------------------------------------------------------------- fetch-review-comments

ME = "me"
T0, T1, T2 = "2026-01-01T00:00:00Z", "2026-01-02T00:00:00Z", "2026-01-03T00:00:00Z"
SELF_ROUTE = (["api", "user"], {"login": ME})
REVIEWS_LIST = ["repos/o/r/pulls/7/reviews"]
COMMENTS_LIST = ["repos/o/r/issues/7/comments"]
COMMENT_URL = "https://github.com/o/r/pull/7#issuecomment-{}"
REVIEW_BODY_URL = "https://github.com/o/r/pull/7#pullrequestreview-{}"


REVIEW_BODY = (
    "Actionable comments posted: 1\n\n"
    "<details>\n<summary>⚠️ Outside diff range comments (1)</summary><blockquote>\n\n"
    "Outside finding text\n\n</blockquote></details>\n"
    "<details>\n<summary>🧹 Nitpick comments (1)</summary><blockquote>\n\nNit finding text\n\n"
    "</blockquote></details>\n\n🤖 Prompt for all review comments with AI agents\n\nprompt"
)


def _pages(*pages: list) -> str:
    """A paginated REST list as `gh api --paginate` prints it: one JSON array per page."""
    return "\n".join(json.dumps(p) for p in pages)


def _node(login: str | None, body: str, url: str, created: str = T0) -> dict:
    return {"author": None if login is None else {"login": login}, "body": body, "url": url, "createdAt": created}


def _thread(path: str, *nodes: dict, resolved: bool = False, more: str | None = None) -> dict:
    """A review thread; `more` is the cursor of a further page of its comments."""
    return {"id": f"T_{path}", "isResolved": resolved, "isOutdated": False, "path": path, "line": 10,
            "originalLine": 10,
            "comments": {"pageInfo": {"hasNextPage": more is not None, "endCursor": more}, "nodes": list(nodes)}}


def _threads_page(*threads: dict, more: str | None = None) -> dict:
    return {"data": {"repository": {"pullRequest": {"reviewThreads": {
        "pageInfo": {"hasNextPage": more is not None, "endCursor": more}, "nodes": list(threads)}}}}}


def _rest_review(rid: int, login: str | None, body: str, submitted: str = T0) -> dict:
    return {"id": rid, "user": None if login is None else {"login": login}, "body": body,
            "html_url": REVIEW_BODY_URL.format(rid), "submitted_at": submitted}


def _rest_comment(cid: int, login: str | None, body: str, created: str = T0) -> dict:
    return {"id": cid, "user": None if login is None else {"login": login}, "body": body,
            "html_url": COMMENT_URL.format(cid), "created_at": created}


def _fetch_comments(fake_gh, run_script, threads=None, reviews=(), comments=()) -> tuple[str, dict]:
    """Run the fetcher; returns its Markdown and its JSON."""
    graphql = threads if isinstance(threads, dict) else _threads_page(*(threads or ()))
    fake_gh.route(SELF_ROUTE, (["graphql"], graphql), (REVIEWS_LIST, list(reviews)),
                  (COMMENTS_LIST, list(comments)))
    r = run_script("fetch-review-comments.sh", "7", *REPO)
    assert r.returncode == 0, r.stderr
    return r.stdout, json.loads(_json_path(r.stdout).read_text())


def _authors(entries: list[dict]) -> list[str]:
    return [e["author"] for e in entries]


def test_review_comments_every_author_but_the_logged_in_user(fake_gh, run_script):
    threads = [_thread("a.py", _node("alice", "Rename this", "https://x/a")),
               _thread("b.py", _node("bob", "Old news", "https://x/b"), resolved=True),
               _thread("c.py", _node(ME, "Note to self", "https://x/c"))]
    reviews = [_rest_review(51, "copilot-pull-request-reviewer[bot]", "Consider X"),
               _rest_review(52, "coderabbitai[bot]", REVIEW_BODY), _rest_review(53, ME, "My own review"),
               _rest_review(54, "dave", " \n")]
    comments = [_rest_comment(41, "bob", "Why this?"), _rest_comment(42, "sonarqubecloud[bot]", "Quality Gate passed"),
                _rest_comment(43, ME, "Pushed a fix")]
    out, data = _fetch_comments(fake_gh, run_script, threads, reviews, comments)
    assert list(data) == ["pr", "repo", "threads", "reviews", "comments", "nitpicks", "outside_diff"]
    assert [t["id"] for t in data["threads"]] == ["T_a.py"]
    assert _authors(data["reviews"]) == ["copilot-pull-request-reviewer[bot]"]
    assert data["reviews"][0] == {"author": "copilot-pull-request-reviewer[bot]", "url": REVIEW_BODY_URL.format(51),
                                  "createdAt": T0, "body": "Consider X", "answered": False}
    assert _authors(data["comments"]) == ["bob", "sonarqubecloud[bot]"]
    assert data["comments"][0] == {"author": "bob", "url": COMMENT_URL.format(41), "createdAt": T0,
                                   "body": "Why this?", "answered": False}
    assert _json_path(out).name.startswith("review-comments-7-")
    for heading in ("## Review bodies", "## Conversation comments", "## CodeRabbit review-summary nitpicks",
                    "## CodeRabbit outside-diff-range comments"):
        assert heading in out
    for shown in ("Rename this", "Consider X", "Why this?"):
        assert shown in out
    for hidden in ("Old news", "Note to self", "My own review", "Pushed a fix"):
        assert hidden not in out


def test_review_comments_thread_answered_by_its_last_comment(fake_gh, run_script):
    threads = [_thread("a.py", _node("alice", "Fix", "https://x/a1"), _node(ME, "Fixed", "https://x/a2", T1)),
               _thread("b.py", _node("alice", "Fix", "https://x/b1"), _node(ME, "Fixed", "https://x/b2", T1),
                       _node("alice", "Not quite", "https://x/b3", T2))]
    _, data = _fetch_comments(fake_gh, run_script, threads)
    assert [(t["id"], t["answered"]) for t in data["threads"]] == [("T_a.py", True), ("T_b.py", False)]


def test_review_comments_answered_by_a_later_re_line(fake_gh, run_script):
    reviews = [_rest_review(51, "copilot-pull-request-reviewer[bot]", "Consider X")]
    comments = [_rest_comment(41, "bob", "Why this?"), _rest_comment(42, "carol", "And this?"),
                _rest_comment(43, "erin", "Also?"),
                _rest_comment(61, ME, f"Re: {COMMENT_URL.format(41)}\n\nBecause.", T1),
                _rest_comment(62, ME, f"Thanks.\nRe: {REVIEW_BODY_URL.format(51)}", T1),
                _rest_comment(63, ME, f"Re: {COMMENT_URL.format(42)} too", T1),
                _rest_comment(64, ME, f"Re: {COMMENT_URL.format(43)}0", T1)]
    _, data = _fetch_comments(fake_gh, run_script, reviews=reviews, comments=comments)
    assert [(c["author"], c["answered"]) for c in data["comments"]] == [("bob", True), ("carol", False),
                                                                        ("erin", False)]
    assert [r["answered"] for r in data["reviews"]] == [False]


def test_review_comments_a_reply_older_than_the_comment_does_not_answer_it(fake_gh, run_script):
    comments = [_rest_comment(61, ME, f"Re: {COMMENT_URL.format(41)}", T0), _rest_comment(41, "bob", "Why?", T1)]
    _, data = _fetch_comments(fake_gh, run_script, comments=comments)
    assert [(c["author"], c["answered"]) for c in data["comments"]] == [("bob", False)]


def test_review_comments_deleted_account_is_ghost(fake_gh, run_script):
    threads = [_thread("a.py", _node(None, "Fix", "https://x/a"))]
    out, data = _fetch_comments(fake_gh, run_script, threads, [_rest_review(51, None, "Consider X")],
                                [_rest_comment(41, None, "Why?")])
    assert [n["author"]["login"] for n in data["threads"][0]["comments"]["nodes"]] == ["ghost"]
    assert _authors(data["reviews"]) == ["ghost"]
    assert _authors(data["comments"]) == ["ghost"]
    assert "ghost" in out


INNER_PAGE = ["graphql", "threadId=T_a.py", "cursor=c1"]


def test_review_comments_read_every_page(fake_gh, run_script):
    first = _threads_page(_thread("a.py", _node("alice", "a-1", "https://x/a1"), more="c1"), more="p1")
    second = _threads_page(_thread("b.py", _node("bob", "b-1", "https://x/b1")))
    inner = {"data": {"node": {"comments": {"pageInfo": {"hasNextPage": False, "endCursor": None},
                                            "nodes": [_node("alice", "a-2", "https://x/a2", T1)]}}}}
    fake_gh.route(SELF_ROUTE, (INNER_PAGE, inner),
                  {"match": ["graphql"], "responses": [{"stdout": first}, {"stdout": second}]},
                  (REVIEWS_LIST, _pages([_rest_review(51, "alice", "r-1")], [_rest_review(52, "bob", "r-2")])),
                  (COMMENTS_LIST, _pages([_rest_comment(41, "alice", "c-1")], [_rest_comment(42, "bob", "c-2")])))
    r = run_script("fetch-review-comments.sh", "7", *REPO)
    assert r.returncode == 0, r.stderr
    data = json.loads(_json_path(r.stdout).read_text())
    assert [[n["body"] for n in t["comments"]["nodes"]] for t in data["threads"]] == [["a-1", "a-2"], ["b-1"]]
    assert [x["body"] for x in data["reviews"]] == ["r-1", "r-2"]
    assert [x["body"] for x in data["comments"]] == ["c-1", "c-2"]
    assert [c for c in fake_gh.calls() if all(t in c["argv"] for t in INNER_PAGE)]
    outer = [c["argv"] for c in fake_gh.calls() if "graphql" in c["argv"] and "threadId=T_a.py" not in c["argv"]]
    assert len(outer) == 2
    assert any("p1" in token for token in outer[1])
    lists = [c["argv"] for c in fake_gh.calls() if any(t in c["argv"] for t in (*REVIEWS_LIST, *COMMENTS_LIST))]
    assert len(lists) == 2
    assert all("--paginate" in argv for argv in lists)


def test_review_comments_reject_the_old_all_authors_flag(fake_gh, run_script):
    r = run_script("fetch-review-comments.sh", "7", *REPO, "--all-authors")
    assert r.returncode == 2
    assert fake_gh.calls() == []


@pytest.mark.parametrize("failing", ["user", "graphql", "reviews", "comments"])
def test_review_comments_fail_on_a_failed_read(fake_gh, run_script, failing):
    routes = {"user": SELF_ROUTE, "graphql": (["graphql"], _threads_page()), "reviews": (REVIEWS_LIST, []),
              "comments": (COMMENTS_LIST, [])}
    routes[failing] = (routes[failing][0], "", 1)
    fake_gh.route(*routes.values())
    r = run_script("fetch-review-comments.sh", "7", *REPO)
    assert r.returncode != 0
    assert [c for c in fake_gh.calls() if all(t in c["argv"] for t in routes[failing][0])]
    assert "JSON: " not in r.stdout
    assert not list(fake_gh.tmp.glob("review-comments-*.json"))


GRAPHQL = _threads_page(_thread("src/a.py", _node("coderabbitai", "Fix this", "https://x/src/a.py")),
                        _thread("src/b.py", _node("coderabbitai", "Old news", "https://x/src/b.py"), resolved=True),
                        _thread("src/c.py", _node("someone", "Human note", "https://x/src/c.py")))

REVIEWS = [{"id": 1, "user": {"login": "coderabbitai[bot]"}, "body": REVIEW_BODY, "html_url": "https://x/review/1",
            "submitted_at": "t"}]


def test_review_comments_nitpicks_and_outside_diff(fake_gh, run_script):
    out, data = _fetch_comments(fake_gh, run_script, GRAPHQL, REVIEWS)
    assert "## Thread 1 — src/a.py:10" in out
    assert "> Fix this" in out
    assert "## Thread 2 — src/c.py:10" in out
    assert "Human note" in out
    assert "Old news" not in out
    assert "### Nitpick 1" in out
    assert "Nit finding text" in out
    assert "### Outside-diff 1" in out
    assert "Outside finding text" in out
    assert [t["path"] for t in data["threads"]] == ["src/a.py", "src/c.py"]
    assert data["reviews"] == []
    assert [n["url"] for n in data["nitpicks"]] == ["https://x/review/1"]


def test_review_comments_with_a_body_larger_than_an_argument(fake_gh, run_script):
    body = "big " * 50_000
    _, data = _fetch_comments(fake_gh, run_script, [_thread("src/a.py", _node("coderabbitai", body, "https://x/a"))])
    assert data["threads"][0]["comments"]["nodes"][0]["body"] == body


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
SNAPSHOT = ["pr", "view", "headRefOid,mergeable,statusCheckRollup"]
TESTS_RUN = {"__typename": "CheckRun", "name": "tests", "status": "COMPLETED"}
CR_CONTEXT = {"__typename": "StatusContext", "context": "CodeRabbit", "state": "SUCCESS"}
SONAR_RUN = {"__typename": "CheckRun", "name": "SonarCloud Code Analysis", "status": "COMPLETED",
             "detailsUrl": "https://sonarcloud.io/dashboard?id=url_key&pullRequest=7"}
CR_USER = {"login": "coderabbitai[bot]"}
PR_URL = "https://github.com/o/r/pull/7"
OWN_COMMENTS = [{"id": 30, "user": {"login": ME}, "html_url": f"{PR_URL}#issuecomment-30",
                 "updated_at": "2026-01-02T00:00:00Z", "body": "LGTM"}]
SUMMARIZE = "<!-- This is an auto-generated comment: summarize by coderabbit.ai -->"
CR_REVIEW = "<!-- coderabbit-ai-generated:v1 -->\n**Actionable comments posted: 1**"
RETRIGGER = "'gh pr comment 7 --repo o/r --body \"@coderabbitai review\"'"
SUMMARY_ITEM = f"pr-comment coderabbitai[bot] {PR_URL}#issuecomment-31\n"
REPLY_ITEM = f"pr-comment coderabbitai[bot] {PR_URL}#issuecomment-32\n"
RUNNING = {**TESTS_RUN, "name": "lint", "status": "IN_PROGRESS", "detailsUrl": "https://github.com/o/r/actions/runs/1/job/9"}
COMMENT_LISTS = ("repos/o/r/issues/7/comments", "repos/o/r/pulls/7/reviews", "repos/o/r/pulls/7/comments")
_ABSENT = object()


def _settled(outcome: str, head: str = HEAD) -> str:
    return f"coderabbit-settled {head[:7]} {outcome}\n"


def _ci_failed(url: str, name: str, head: str = HEAD) -> str:
    return f"ci-failed {head[:7]} {url} {name}\n"


def _coverage(sha: str) -> str:
    return f'<!-- final_review_risk_coverage:{{"sourceCommitId":"{sha}","coveredCommitId":"{sha}","kind":"reviewed"}} -->'


def _summary(text: str = "## Summary", *, covers: str | None = None) -> dict:
    body = "\n".join([SUMMARIZE, text, *([_coverage(covers)] if covers else [])])
    return {"id": 31, "user": CR_USER, "html_url": f"{PR_URL}#issuecomment-31", "updated_at": "2026-01-02T00:00:00Z",
            "body": body}


def _cr_reply(body: str) -> dict:
    return {"id": 32, "user": CR_USER, "html_url": f"{PR_URL}#issuecomment-32", "updated_at": "2026-01-03T00:00:00Z",
            "body": body}


def _conversation(cid: int, login: str | None, body: str = "a comment") -> dict:
    return {"id": cid, "user": None if login is None else {"login": login}, "html_url": f"{PR_URL}#issuecomment-{cid}",
            "updated_at": "2026-01-02T00:00:00Z", "body": body}


def _status(description: str, state: str = "success", context: str = "CodeRabbit") -> dict:
    return {"context": context, "state": state, "description": description}


def _review(body: str = CR_REVIEW, *, commit: str = HEAD, login: str = "coderabbitai[bot]", rid: int = 21) -> dict:
    return {"id": rid, "user": {"login": login}, "commit_id": commit, "body": body,
            "html_url": f"{PR_URL}#pullrequestreview-{rid}"}


def _review_comment(cid: int, login: str | None = "coderabbitai[bot]") -> dict:
    return {"id": cid, "user": None if login is None else {"login": login}, "html_url": f"{PR_URL}#discussion_r{cid}",
            "updated_at": "2026-01-02T00:00:00Z", "body": f"comment {cid}"}


def _suite(slug: str, status: str, conclusion: str | None = None) -> dict:
    return {"app": {"slug": slug}, "status": status, "conclusion": conclusion}


def _failed_run(name: str, job: int) -> dict:
    return {**TESTS_RUN, "name": name, "conclusion": "FAILURE",
            "detailsUrl": f"https://github.com/o/r/actions/runs/1/job/{job}"}


def _snapshot(head: str = HEAD, rollup=(TESTS_RUN, CR_CONTEXT), mergeable: object = "MERGEABLE") -> dict:
    snapshot = {"headRefOid": head, "statusCheckRollup": list(rollup)}
    return snapshot if mergeable is _ABSENT else {**snapshot, "mergeable": mergeable}


def _routes(*, head: str = HEAD, rollup=(TESTS_RUN, CR_CONTEXT), suites=(), comments=(), statuses=(),
            reviews=(), review_comments=(), mergeable: object = "MERGEABLE") -> dict[str, Any]:
    """The wait's reads by name: HEAD's snapshot, the logged-in user, HEAD's suites and statuses; issue comments,
    reviews, review comments."""
    return {
        "snapshot": (SNAPSHOT, _snapshot(head, rollup, mergeable)),
        "user": SELF_ROUTE,
        "suites": ([f"repos/o/r/commits/{head}/check-suites"], {"check_suites": list(suites)}),
        "comments": (["repos/o/r/issues/7/comments"], list(comments)),
        "statuses": ([f"repos/o/r/commits/{head}/statuses"], list(statuses)),
        "reviews": (["repos/o/r/pulls/7/reviews"], list(reviews)),
        "review_comments": (["repos/o/r/pulls/7/comments"], list(review_comments)),
    }


@pytest.fixture
def fast_wait(monkeypatch, git_repo):
    for name in ("LA_WAIT_GATE_TIMEOUT", "LA_WAIT_POLL_SECONDS", "LA_WAIT_CR_SETTLE"):
        monkeypatch.setenv(name, "0")


def _wait(fake_gh, run_script, routes: dict) -> subprocess.CompletedProcess[str]:
    fake_gh.route(*routes.values())
    return run_script("wait-for-reviews.sh", "7", *REPO)


@pytest.mark.usefixtures("fast_wait")
def test_wait_gate_clear_without_coderabbit(fake_gh, run_script):
    r = _wait(fake_gh, run_script, _routes(rollup=[TESTS_RUN], comments=OWN_COMMENTS))
    assert (r.returncode, r.stdout) == (0, ""), r.stderr


@pytest.mark.usefixtures("fast_wait")
def test_wait_settles_when_coderabbit_only_commented(fake_gh, run_script):
    r = _wait(fake_gh, run_script, _routes(rollup=[TESTS_RUN], comments=[_summary(covers=HEAD)]))
    assert (r.returncode, r.stdout) == (0, SUMMARY_ITEM + _settled("reviewed")), r.stderr


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
    assert (r.returncode, r.stdout) == (1, "")
    assert "could not read the check rollup" in r.stderr


MALFORMED_SNAPSHOTS = [{"headRefOid": HEAD, "statusCheckRollup": {}}, {"headRefOid": HEAD, "statusCheckRollup": "x"},
                       {"headRefOid": HEAD, "statusCheckRollup": None}, {"headRefOid": HEAD}, {"statusCheckRollup": []}]


@pytest.mark.usefixtures("fast_wait")
@pytest.mark.parametrize("snapshot", MALFORMED_SNAPSHOTS)
def test_wait_gate_fails_closed_on_a_malformed_snapshot(fake_gh, run_script, snapshot):
    fake_gh.route((SNAPSHOT, snapshot))
    r = run_script("wait-for-reviews.sh", "7", *REPO)
    assert (r.returncode, r.stdout) == (1, "")
    assert "could not read the check rollup" in r.stderr


def test_wait_requires_pr(run_script):
    assert run_script("wait-for-reviews.sh").returncode == 64


# The gate: Sonar check suites on HEAD


@pytest.mark.usefixtures("fast_wait")
@pytest.mark.parametrize(("slug", "status"), [("sonarqubecloud", "queued"), ("sonarqubecloud", "in_progress"),
                                              ("SonarCloud", "queued")])
def test_wait_gate_waits_for_pending_sonar_suite(fake_gh, run_script, slug, status):
    r = _wait(fake_gh, run_script, _routes(rollup=[TESTS_RUN], suites=[_suite(slug, status)]))
    assert (r.returncode, r.stdout) == (1, "")
    assert f"{slug} (check suite)" in r.stderr


@pytest.mark.usefixtures("fast_wait")
def test_wait_gate_waits_for_sonar_suite_beside_completed_sonar_run(fake_gh, run_script):
    r = _wait(fake_gh, run_script, _routes(rollup=[TESTS_RUN, SONAR_RUN], suites=[_suite("sonarqubecloud", "queued")]))
    assert (r.returncode, r.stdout) == (1, "")
    assert "sonarqubecloud (check suite)" in r.stderr


@pytest.mark.usefixtures("fast_wait")
def test_wait_gate_clears_on_completed_sonar_suite_beside_idle_apps(fake_gh, run_script):
    suites = [_suite("sonarqubecloud", "completed", "success"), _suite("github-actions", "queued")]
    r = _wait(fake_gh, run_script, _routes(rollup=[TESTS_RUN], suites=suites, comments=OWN_COMMENTS))
    assert (r.returncode, r.stdout) == (0, "sonar-done abc success\n"), r.stderr


@pytest.mark.usefixtures("fast_wait")
def test_wait_sonar_done_names_the_first_non_success_conclusion(fake_gh, run_script):
    suites = [_suite("sonarqubecloud", "completed", conclusion) for conclusion in ("success", "neutral", "failure")]
    r = _wait(fake_gh, run_script, _routes(rollup=[TESTS_RUN], suites=suites, comments=OWN_COMMENTS))
    assert (r.returncode, r.stdout) == (0, "sonar-done abc neutral\n"), r.stderr


@pytest.mark.usefixtures("fast_wait")
@pytest.mark.parametrize("suites_route",[("", 1), ({"check_suites": ["{not json"]}, 0)], ids=["fails", "invalid"])
def test_wait_gate_stays_closed_when_suites_unreadable(fake_gh, run_script, suites_route):
    routes = _routes(rollup=[TESTS_RUN], comments=OWN_COMMENTS)
    routes["suites"] = (routes["suites"][0], *suites_route)
    r = _wait(fake_gh, run_script, routes)
    assert (r.returncode, r.stdout) == (1, "")
    assert [c for c in fake_gh.calls() if "repos/o/r/commits/abc/check-suites" in c["argv"]]


# CodeRabbit evidence keyed to HEAD


@pytest.mark.usefixtures("fast_wait")
def test_wait_settles_when_summary_covers_head(fake_gh, run_script):
    r = _wait(fake_gh, run_script, _routes(comments=[_summary(covers=HEAD)]))
    assert (r.returncode, r.stdout) == (0, SUMMARY_ITEM + _settled("reviewed")), r.stderr


@pytest.mark.usefixtures("fast_wait")
def test_wait_placeholder_summary_does_not_settle(fake_gh, run_script):
    r = _wait(fake_gh, run_script, _routes(comments=[_summary()]))
    assert (r.returncode, r.stdout) == (0, SUMMARY_ITEM + _settled("cap")), r.stderr


@pytest.mark.usefixtures("fast_wait")
def test_wait_settles_on_completed_status_without_coverage(fake_gh, run_script):
    r = _wait(fake_gh, run_script, _routes(comments=[_summary(covers="prev")], statuses=[_status("Review completed")]))
    assert (r.returncode, r.stdout) == (0, SUMMARY_ITEM + _settled("reviewed")), r.stderr


@pytest.mark.usefixtures("fast_wait")
def test_wait_settles_on_review_on_head(fake_gh, run_script):
    r = _wait(fake_gh, run_script, _routes(comments=[_summary()], reviews=[_review()]))
    assert (r.returncode, r.stdout) == (0, f"review coderabbitai[bot] {PR_URL}#pullrequestreview-21\n" + SUMMARY_ITEM
                                          + _settled("reviewed"))


@pytest.mark.usefixtures("fast_wait")
@pytest.mark.parametrize(("review", "item"), [
    (_review(""), ""),
    (_review(commit="prev"), f"review coderabbitai[bot] {PR_URL}#pullrequestreview-21\n"),
    (_review(login="alice"), f"review alice {PR_URL}#pullrequestreview-21\n"),
], ids=["empty-body", "other-commit", "other-author"])
def test_wait_ignores_reviews_other_than_coderabbits_on_head(fake_gh, run_script, review, item):
    r = _wait(fake_gh, run_script, _routes(comments=[_summary()], reviews=[review]))
    assert (r.returncode, r.stdout) == (0, item + SUMMARY_ITEM + _settled("cap")), r.stderr


@pytest.mark.usefixtures("fast_wait")
def test_wait_matches_status_descriptions_case_insensitively(fake_gh, run_script):
    r = _wait(fake_gh, run_script, _routes(comments=[_summary()], statuses=[_status("review COMPLETED")]))
    assert (r.returncode, r.stdout) == (0, SUMMARY_ITEM + _settled("reviewed")), r.stderr


@pytest.mark.usefixtures("fast_wait")
def test_wait_ignores_statuses_of_other_contexts(fake_gh, run_script):
    statuses = [_status("Review rate limited", context="other-bot"), _status("Review completed", context="ci")]
    r = _wait(fake_gh, run_script, _routes(comments=[_summary()], statuses=statuses))
    assert (r.returncode, r.stdout) == (0, SUMMARY_ITEM + _settled("cap")), r.stderr


@pytest.mark.usefixtures("fast_wait")
@pytest.mark.parametrize(("comment", "item"), [
    (_cr_reply(f"Sure, reviewing.\n{_coverage(HEAD)}"), REPLY_ITEM),
    (_conversation(33, "alice", f"{SUMMARIZE}\n{_coverage(HEAD)}"), f"pr-comment alice {PR_URL}#issuecomment-33\n"),
], ids=["coderabbit-reply", "human-copy"])
def test_wait_summary_is_coderabbits_summarize_comment(fake_gh, run_script, comment, item):
    r = _wait(fake_gh, run_script, _routes(comments=[_summary(), comment]))
    assert (r.returncode, r.stdout) == (0, SUMMARY_ITEM + item + _settled("cap")), r.stderr


@pytest.mark.usefixtures("fast_wait")
@pytest.mark.parametrize("statuses", [[_status("Review in progress", state="pending")], [_status("Something new")]],
                         ids=["in-progress", "unknown"])
def test_wait_other_statuses_poll_to_cap(fake_gh, run_script, statuses):
    r = _wait(fake_gh, run_script, _routes(comments=[_summary()], statuses=statuses))
    assert (r.returncode, r.stdout) == (0, SUMMARY_ITEM + _settled("cap")), r.stderr


@pytest.mark.usefixtures("fast_wait")
def test_wait_detects_rate_limit(fake_gh, run_script):
    comments = [_summary("Review limit reached", covers="prev"), _cr_reply("@coderabbitai review — on it.")]
    r = _wait(fake_gh, run_script, _routes(comments=comments, statuses=[_status("Review rate limited")]))
    assert (r.returncode, r.stdout) == (3, SUMMARY_ITEM + REPLY_ITEM + _settled("rate-limited"))
    assert "RATE LIMITED" in r.stderr
    assert RETRIGGER in r.stderr


@pytest.mark.usefixtures("fast_wait")
def test_wait_detects_pause(fake_gh, run_script):
    r = _wait(fake_gh, run_script, _routes(comments=[_summary()], statuses=[_status("Review paused")]))
    assert (r.returncode, r.stdout) == (3, SUMMARY_ITEM + _settled("paused"))
    assert "PAUSED" in r.stderr
    assert RETRIGGER in r.stderr


@pytest.mark.usefixtures("fast_wait")
@pytest.mark.parametrize(("statuses", "outcome"), [
    ([_status("Review paused"), _status("Review rate limited")], "paused"),
    ([_status("Review rate limited"), _status("Review paused")], "rate-limited"),
], ids=["paused-latest", "rate-limited-latest"])
def test_wait_latest_status_decides(fake_gh, run_script, statuses, outcome):
    r = _wait(fake_gh, run_script, _routes(comments=[_summary()], statuses=statuses))
    assert (r.returncode, r.stdout) == (3, SUMMARY_ITEM + _settled(outcome))


@pytest.mark.usefixtures("fast_wait")
def test_wait_carried_forward(fake_gh, run_script):
    r = _wait(fake_gh, run_script, _routes(comments=[_summary(covers="prev")],
                                           statuses=[_status("Prior review carried forward")]))
    assert (r.returncode, r.stdout) == (0, SUMMARY_ITEM + _settled("carried-forward")), r.stderr


@pytest.mark.usefixtures("fast_wait")
@pytest.mark.parametrize(("statuses", "comments"), [
    ([_status("Review rate limited"), _status("Review completed")], [_summary()]),
    ([_status("Review paused")], [_summary(covers=HEAD)]),
    ([_status("Prior review carried forward")], [_summary(covers=HEAD)]),
], ids=["completed-then-rate-limited", "paused-but-covered", "carried-forward-but-covered"])
def test_wait_reviewed_wins(fake_gh, run_script, statuses, comments):
    r = _wait(fake_gh, run_script, _routes(comments=comments, statuses=statuses))
    assert (r.returncode, r.stdout) == (0, SUMMARY_ITEM + _settled("reviewed")), r.stderr


@pytest.mark.usefixtures("fast_wait")
def test_wait_stale_rate_limit_text_with_fresh_reply(fake_gh, run_script):
    comments = [_summary("Review limit reached", covers="prev"), _cr_reply("Sure!")]
    r = _wait(fake_gh, run_script, _routes(comments=comments))
    assert (r.returncode, r.stdout) == (0, SUMMARY_ITEM + REPLY_ITEM + _settled("cap")), r.stderr


@pytest.mark.usefixtures("fast_wait")
def test_wait_names_head_by_its_short_sha(fake_gh, run_script):
    head = "0123456789abcdef0123456789abcdef01234567"
    r = _wait(fake_gh, run_script, _routes(head=head, comments=[_summary(covers=head)]))
    assert (r.returncode, r.stdout) == (0, SUMMARY_ITEM + "coderabbit-settled 0123456 reviewed\n"), r.stderr


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


@pytest.mark.usefixtures("fast_wait")
@pytest.mark.parametrize("terminal", ["Review rate limited", "Review paused", "Prior review carried forward"])
@pytest.mark.parametrize("source", ["snapshot", "suites", "comments", "statuses", "reviews", "statuses-invalid"])
def test_wait_failed_read_is_never_an_answer(fake_gh, run_script, source, terminal):
    routes = _routes(comments=[_summary()], statuses=[_status(terminal)])
    if source == "statuses-invalid":
        # jq -r prints the string raw, so the script reads the malformed line `{not json`.
        routes["statuses"] = (routes["statuses"][0], ["{not json"])
    else:
        routes[source] = (routes[source][0], "", 1)
    r = _wait(fake_gh, run_script, routes)
    # A failed snapshot or suites read also keeps the gate closed until its timeout.
    items = "" if source in ("snapshot", "comments") else SUMMARY_ITEM
    expected = (1, items) if source in ("snapshot", "suites") else (0, items + _settled("cap"))
    actual = (r.returncode, r.stdout)
    assert actual == expected, r.stderr


@pytest.mark.usefixtures("fast_wait")
@pytest.mark.parametrize(("failing", "comments", "statuses", "items"), [
    ("statuses", [_summary(covers=HEAD)], [], SUMMARY_ITEM),
    ("reviews", [_summary()], [_status("Review completed")], SUMMARY_ITEM),
    ("comments", [], [_status("Review completed")], ""),
])
def test_wait_reviewed_stands_on_the_reads_that_succeeded(fake_gh, run_script, failing, comments, statuses, items):
    routes = _routes(comments=comments, statuses=statuses)
    routes[failing] = (routes[failing][0], "", 1)
    r = _wait(fake_gh, run_script, routes)
    assert (r.returncode, r.stdout) == (0, items + _settled("reviewed")), r.stderr


@pytest.mark.usefixtures("git_repo")
def test_wait_keeps_polling_after_a_failed_read(fake_gh, run_script, monkeypatch):
    monkeypatch.setenv("LA_WAIT_GATE_TIMEOUT", "0")
    monkeypatch.setenv("LA_WAIT_POLL_SECONDS", "0")
    routes = _routes(comments=[_summary()])
    routes["statuses"] = {"match": routes["statuses"][0],
                          "responses": [{"stdout": "", "exit": 1}, {"stdout": [_status("Review completed")]}]}
    r = _wait(fake_gh, run_script, routes)
    assert (r.returncode, r.stdout) == (0, SUMMARY_ITEM + _settled("reviewed")), r.stderr


@pytest.mark.usefixtures("fast_wait")
def test_wait_restarts_when_head_moves(fake_gh, run_script, monkeypatch):
    monkeypatch.setenv("LA_WAIT_CR_SETTLE", "600")
    abc, defs = _routes(), _routes(head="def", statuses=[_status("Review completed")])
    snapshots = [{"stdout": abc["snapshot"][1]}, {"stdout": defs["snapshot"][1]}]
    fake_gh.route({"match": SNAPSHOT, "responses": snapshots}, abc["user"], abc["suites"], defs["suites"],
                  abc["statuses"], defs["statuses"], (abc["comments"][0], [_summary()]), abc["reviews"],
                  abc["review_comments"])
    r = run_script("wait-for-reviews.sh", "7", *REPO)
    expected = SUMMARY_ITEM + "head-moved abc def\n" + _settled("reviewed", "def")
    assert (r.returncode, r.stdout) == (0, expected), r.stderr
    assert [c for c in fake_gh.calls() if "repos/o/r/commits/def/check-suites" in c["argv"]]


# Items, printed once per key across runs


def _state_file(fake_gh) -> Path:
    rel = subprocess.run(["git", "rev-parse", "--git-path", "la/reviews/o/r/7.json"], cwd=fake_gh.tmp,
                         capture_output=True, text=True, check=True).stdout.strip()
    return fake_gh.tmp / rel


@pytest.mark.usefixtures("fast_wait")
def test_wait_second_run_prints_nothing_new(fake_gh, run_script):
    routes = _routes(rollup=[_failed_run("tests", 2), CR_CONTEXT], comments=[_summary()],
                     suites=[_suite("sonarqubecloud", "completed", "success")],
                     statuses=[_status("Review completed")], reviews=[_review(commit="prev")],
                     review_comments=[_review_comment(11)])
    first = _wait(fake_gh, run_script, routes)
    assert (first.returncode, first.stdout) == (0, _ci_failed(routes["snapshot"][1]["statusCheckRollup"][0]["detailsUrl"],
                                                              "tests")
                                                + f"review-comment coderabbitai[bot] {PR_URL}#discussion_r11\n"
                                                + f"review coderabbitai[bot] {PR_URL}#pullrequestreview-21\n" + SUMMARY_ITEM
                                                + "sonar-done abc success\n" + _settled("reviewed")), first.stderr
    assert _state_file(fake_gh).is_file()
    second = _wait(fake_gh, run_script, routes)
    assert (second.returncode, second.stdout) == (0, "")


@pytest.mark.usefixtures("git_repo")
def test_wait_keeps_keys_of_a_concurrent_run(fake_gh, run_script, monkeypatch):
    monkeypatch.setenv("LA_WAIT_POLL_SECONDS", "0")
    tests_failed, lint_failed = _failed_run("tests", 2), _failed_run("lint", 9)
    other = _wait(fake_gh, run_script, _routes(rollup=[tests_failed], comments=OWN_COMMENTS))
    assert other.stdout == _ci_failed(tests_failed["detailsUrl"], "tests"), other.stderr
    state = _state_file(fake_gh)
    others_keys = fake_gh.tmp / "others-keys.json"
    state.rename(others_keys)

    # The fake gh, wrapped to write the other run's state file as this run's second poll starts.
    gh, real, count = fake_gh.bin / "gh", fake_gh.bin / "gh-real", fake_gh.tmp / "snapshots"
    gh.rename(real)
    gh.write_text(
        "#!/usr/bin/env bash\n"
        'if [[ "$1 $2" == "pr view" ]]; then\n'
        f'  n=$(( $(cat "{count}" 2>/dev/null || echo 0) + 1 )); echo "$n" > "{count}"\n'
        f'  if (( n == 2 )); then cp "{others_keys}" "{state}"; fi\n'
        "fi\n"
        f'exec "{real}" "$@"\n', encoding="utf-8")
    gh.chmod(0o755)
    running = {**TESTS_RUN, "name": "lint", "status": "IN_PROGRESS"}
    snapshots = [{"stdout": _snapshot(rollup=rollup)} for rollup in ([running], [lint_failed])]
    routes = _routes(comments=OWN_COMMENTS)
    routes["snapshot"] = {"match": SNAPSHOT, "responses": snapshots}
    fake_gh.route(*routes.values())
    this = run_script("wait-for-reviews.sh", "7", *REPO)
    assert (this.returncode, this.stdout) == (0, _ci_failed(lint_failed["detailsUrl"], "lint")), this.stderr
    assert count.read_text().strip() == "2"

    later = _wait(fake_gh, run_script, _routes(rollup=[tests_failed, lint_failed], comments=OWN_COMMENTS))
    assert (later.returncode, later.stdout) == (0, "")


# Merge conflict


def _slow_gate(monkeypatch, timeout: str = "600") -> None:
    """Instant polls, but neither the gate timeout nor the CodeRabbit cap ends the run."""
    monkeypatch.setenv("LA_WAIT_GATE_TIMEOUT", timeout)
    monkeypatch.setenv("LA_WAIT_POLL_SECONDS", "0")
    monkeypatch.setenv("LA_WAIT_CR_SETTLE", "600")


def _polls(routes: dict, *snapshots: dict) -> dict:
    """`routes` with the snapshot read serving `snapshots` in order, the last repeating."""
    return {**routes, "snapshot": {"match": SNAPSHOT, "responses": [{"stdout": s} for s in snapshots]}}


def _snapshot_calls(fake_gh) -> int:
    return sum(all(t in c["argv"] for t in SNAPSHOT) for c in fake_gh.calls())


CONFLICT = "merge-conflict abc\n"


@pytest.mark.usefixtures("git_repo")
@pytest.mark.parametrize("timeout", ["600", "0"], ids=["gate-pending", "gate-timed-out"])
def test_wait_merge_conflict_while_a_check_runs(fake_gh, run_script, monkeypatch, timeout):
    _slow_gate(monkeypatch, timeout)
    routes = _routes(rollup=[RUNNING, CR_CONTEXT], comments=[_summary()], review_comments=[_review_comment(13, "alice")],
                     mergeable="CONFLICTING")
    r = _wait(fake_gh, run_script, routes)
    assert (r.returncode, r.stdout) == (4, CONFLICT), r.stderr
    assert all(word in r.stderr.lower() for word in ("conflict", "base", "merge"))
    assert [c["argv"] for c in fake_gh.calls() if not all(t in c["argv"] for t in SNAPSHOT)] == []
    assert not _state_file(fake_gh).exists()


@pytest.mark.usefixtures("git_repo")
def test_wait_merge_conflict_during_the_settle(fake_gh, run_script, monkeypatch):
    _slow_gate(monkeypatch)
    r = _wait(fake_gh, run_script, _polls(_routes(), _snapshot(), _snapshot(mergeable="CONFLICTING")))
    assert (r.returncode, r.stdout) == (4, CONFLICT), r.stderr
    assert _snapshot_calls(fake_gh) == 2


@pytest.mark.usefixtures("fast_wait")
@pytest.mark.parametrize("mergeable", ["UNKNOWN", "MERGEABLE", _ABSENT, None, True, ["CONFLICTING"]],
                         ids=["unknown", "mergeable", "missing", "null", "boolean", "list"])
def test_wait_only_a_conflicting_state_is_a_conflict(fake_gh, run_script, mergeable):
    r = _wait(fake_gh, run_script, _routes(rollup=[TESTS_RUN], comments=OWN_COMMENTS, mergeable=mergeable))
    assert (r.returncode, r.stdout) == (0, ""), r.stderr


@pytest.mark.usefixtures("git_repo")
def test_wait_unknown_then_conflicting(fake_gh, run_script, monkeypatch):
    _slow_gate(monkeypatch)
    routes = _polls(_routes(rollup=[RUNNING]), _snapshot(rollup=[RUNNING], mergeable="UNKNOWN"),
                    _snapshot(rollup=[RUNNING], mergeable="CONFLICTING"))
    r = _wait(fake_gh, run_script, routes)
    assert (r.returncode, r.stdout) == (4, CONFLICT), r.stderr
    assert _snapshot_calls(fake_gh) == 2


@pytest.mark.usefixtures("git_repo")
def test_wait_conflict_prints_no_other_item(fake_gh, run_script, monkeypatch):
    _slow_gate(monkeypatch)
    failed = _failed_run("tests", 2)
    routes = _routes(rollup=[failed], review_comments=[_review_comment(13, "alice")], mergeable="CONFLICTING")
    first = _wait(fake_gh, run_script, routes)
    assert (first.returncode, first.stdout) == (4, CONFLICT), first.stderr
    assert not _state_file(fake_gh).exists()
    later = _wait(fake_gh, run_script, {**routes, "snapshot": (SNAPSHOT, _snapshot(rollup=[failed]))})
    expected = _ci_failed(failed["detailsUrl"], "tests") + f"review-comment alice {PR_URL}#discussion_r13\n"
    assert (later.returncode, later.stdout) == (0, expected), later.stderr


@pytest.mark.usefixtures("git_repo")
def test_wait_head_moved_onto_a_conflict(fake_gh, run_script, monkeypatch):
    _slow_gate(monkeypatch)
    routes = _polls(_routes(rollup=[RUNNING]), _snapshot(rollup=[RUNNING]),
                    _snapshot("def", [RUNNING], mergeable="CONFLICTING"))
    r = _wait(fake_gh, run_script, routes)
    assert (r.returncode, r.stdout) == (4, "head-moved abc def\nmerge-conflict def\n"), r.stderr


@pytest.mark.usefixtures("fast_wait")
def test_wait_second_run_reports_the_conflict_again(fake_gh, run_script):
    routes = _routes(rollup=[RUNNING], mergeable="CONFLICTING")
    first = _wait(fake_gh, run_script, routes)
    second = _wait(fake_gh, run_script, routes)
    assert [(r.returncode, r.stdout) for r in (first, second)] == [(4, CONFLICT), (4, CONFLICT)]


# Comment items from every author


@pytest.mark.usefixtures("fast_wait")
def test_wait_comment_items_from_every_author_but_the_logged_in_user(fake_gh, run_script):
    routes = _routes(rollup=[TESTS_RUN], review_comments=[_review_comment(13, "alice"), _review_comment(14, ME)],
                     reviews=[_review("Please split this", login="alice", rid=23),
                              _review("Self review", login=ME, rid=24), _review(" \n", login="carol", rid=25)],
                     comments=[_conversation(31, "bob"), _conversation(32, "sonarqubecloud[bot]"),
                               _conversation(33, ME)])
    r = _wait(fake_gh, run_script, routes)
    assert (r.returncode, r.stdout) == (0, (f"review-comment alice {PR_URL}#discussion_r13\n"
                                            f"review alice {PR_URL}#pullrequestreview-23\n"
                                            f"pr-comment bob {PR_URL}#issuecomment-31\n"
                                            f"pr-comment sonarqubecloud[bot] {PR_URL}#issuecomment-32\n")), r.stderr


_NO_USER = {k: v for k, v in _review_comment(16).items() if k != "user"}


@pytest.mark.usefixtures("fast_wait")
@pytest.mark.parametrize(("lists", "line"), [
    ({"review_comments": [_review_comment(13, None)]}, f"review-comment ghost {PR_URL}#discussion_r13\n"),
    ({"review_comments": [_NO_USER]}, f"review-comment ghost {PR_URL}#discussion_r16\n"),
    ({"reviews": [{**_review("Hm", rid=23), "user": None}]}, f"review ghost {PR_URL}#pullrequestreview-23\n"),
    ({"comments": [_conversation(31, None)]}, f"pr-comment ghost {PR_URL}#issuecomment-31\n"),
], ids=["review-comment", "review-comment-without-user", "review", "pr-comment"])
def test_wait_deleted_account_is_ghost(fake_gh, run_script, lists, line):
    r = _wait(fake_gh, run_script, _routes(rollup=[TESTS_RUN], **lists))
    assert (r.returncode, r.stdout) == (0, line), r.stderr


@pytest.mark.usefixtures("git_repo")
def test_wait_comment_items_wait_for_the_logged_in_user(fake_gh, run_script, monkeypatch):
    _slow_gate(monkeypatch)
    lint_failed = {**RUNNING, "status": "COMPLETED", "conclusion": "FAILURE"}
    routes = _polls(_routes(rollup=[RUNNING], review_comments=[_review_comment(13, "alice")]),
                    _snapshot(rollup=[RUNNING]), _snapshot(rollup=[lint_failed]))
    routes["user"] = {"match": SELF_ROUTE[0], "responses": [{"stdout": "", "exit": 1}, {"stdout": SELF_ROUTE[1]}]}
    r = _wait(fake_gh, run_script, routes)
    # The ci-failed line of poll 2 comes first: the comment is printed only once the user is known.
    expected = _ci_failed(lint_failed["detailsUrl"], "lint") + f"review-comment alice {PR_URL}#discussion_r13\n"
    assert (r.returncode, r.stdout) == (0, expected), r.stderr


@pytest.mark.usefixtures("git_repo")
@pytest.mark.parametrize("comments", [OWN_COMMENTS, [_summary(covers=HEAD)]],
                         ids=["coderabbit-absent", "coderabbit-by-comment"])
def test_wait_reads_each_comment_list_once_per_poll(fake_gh, run_script, monkeypatch, comments):
    _slow_gate(monkeypatch)
    r = _wait(fake_gh, run_script, _polls(_routes(rollup=[RUNNING], comments=comments), _snapshot(rollup=[RUNNING]),
                                          _snapshot(rollup=[TESTS_RUN])))
    assert r.returncode == 0, r.stderr
    assert _snapshot_calls(fake_gh) == 2
    assert {e: sum(e in c["argv"] for c in fake_gh.calls()) for e in COMMENT_LISTS} == dict.fromkeys(COMMENT_LISTS, 2)


@pytest.mark.usefixtures("fast_wait")
def test_wait_reads_comment_lists_paginated_without_coderabbit(fake_gh, run_script):
    r = _wait(fake_gh, run_script, _routes(rollup=[TESTS_RUN], comments=OWN_COMMENTS))
    assert r.returncode == 0, r.stderr
    lists = [c["argv"] for c in fake_gh.calls() if any(e in c["argv"] for e in COMMENT_LISTS)]
    assert sorted(e for argv in lists for e in COMMENT_LISTS if e in argv) == sorted(COMMENT_LISTS)
    assert all("--paginate" in argv for argv in lists), lists


@pytest.mark.usefixtures("fast_wait")
def test_wait_prints_comment_items_from_every_page(fake_gh, run_script):
    routes = _routes(rollup=[TESTS_RUN])
    routes["review_comments"] = (routes["review_comments"][0],
                                 _pages([_review_comment(13, "alice")], [_review_comment(15, "bob")]))
    routes["reviews"] = (routes["reviews"][0],
                         _pages([_review("a", login="alice", rid=23)], [_review("b", login="bob", rid=26)]))
    routes["comments"] = (routes["comments"][0], _pages([_conversation(31, "alice")], [_conversation(34, "bob")]))
    r = _wait(fake_gh, run_script, routes)
    assert (r.returncode, r.stdout) == (0, (f"review-comment alice {PR_URL}#discussion_r13\n"
                                            f"review-comment bob {PR_URL}#discussion_r15\n"
                                            f"review alice {PR_URL}#pullrequestreview-23\n"
                                            f"review bob {PR_URL}#pullrequestreview-26\n"
                                            f"pr-comment alice {PR_URL}#issuecomment-31\n"
                                            f"pr-comment bob {PR_URL}#issuecomment-34\n")), r.stderr


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
    assert _reviewers(fake_gh, run_script, [TESTS_RUN, CR_CONTEXT], OWN_COMMENTS)["coderabbit"] is True


@pytest.mark.usefixtures("git_repo")
def test_pr_reviewers_coderabbit_by_comment(fake_gh, run_script):
    comments = [{"user": CR_USER, "updated_at": "t", "body": "## Summary"}]
    assert _reviewers(fake_gh, run_script, [TESTS_RUN], comments)["coderabbit"] is True


@pytest.mark.usefixtures("git_repo")
def test_pr_reviewers_no_bots(fake_gh, run_script):
    out = _reviewers(fake_gh, run_script, [TESTS_RUN], OWN_COMMENTS, suites=[_suite("github-actions", "completed")])
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
        f"format: {current_format('living-architecture.yaml')}\nreviewers: {{sonar: {{project_key: cfg_key}}}}\n", encoding="utf-8")
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


@pytest.mark.usefixtures("git_repo")
@pytest.mark.parametrize("snapshot", MALFORMED_SNAPSHOTS)
def test_pr_reviewers_malformed_snapshot(fake_gh, run_script, snapshot):
    fake_gh.route((SNAPSHOT, snapshot))
    r = run_script("pr-reviewers.sh", "7", *REPO)
    assert (r.returncode, r.stdout) == (2, "")


@pytest.mark.parametrize("args", [[], ["abc", *REPO], ["-3", *REPO]])
def test_pr_reviewers_rejects_missing_or_bad_pr(fake_gh, run_script, args):
    r = run_script("pr-reviewers.sh", *args)
    assert r.returncode == 2
    assert r.stdout == ""
    assert fake_gh.calls() == []
