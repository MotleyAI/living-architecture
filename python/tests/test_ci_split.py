"""The sharded CI jobs: the workflow's shape and the partition each shard split makes."""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CI = PROJECT_ROOT.parent / ".github" / "workflows" / "ci.yml"
DURATIONS = "tests/durations"
CONFORMANCE_CASES = "tests/test_conformance.py::test_case"
# Per job kind: shard count, environment and pytest arguments, as the CI job runs them.
KINDS = {
    "suite": (2, {}, ["--deselect", CONFORMANCE_CASES]),
    "cross-python": (3, {"LA_CONFORMANCE_CROSS": "1", "LA_CONFORMANCE_TWIN": "python"}, ["tests/test_conformance.py"]),
    "cross-typescript": (3, {"LA_CONFORMANCE_CROSS": "1", "LA_CONFORMANCE_TWIN": "typescript"},
                         ["tests/test_conformance.py"]),
}


def _jobs() -> dict:
    return yaml.safe_load(CI.read_text(encoding="utf-8"))["jobs"]


def _normal(text: str) -> str:
    """`text` with each `${{ expr }}` written `${{expr}}`."""
    return re.sub(r"\$\{\{\s*(.*?)\s*\}\}", r"${{\1}}", text)


def _step(job: dict, command: str) -> dict:
    [step] = [s for s in job["steps"] if _normal(s.get("run", "")).split()[:len(command.split())] == command.split()]
    return step


def _option(run: str, name: str) -> str:
    tokens = _normal(run).split()
    assert tokens.count(name) == 1, run
    return tokens[tokens.index(name) + 1]


def _condition(step: dict) -> str | None:
    condition = step.get("if")
    return None if condition is None else re.sub(r"^\$\{\{(.*)\}\}$", r"\1", _normal(str(condition))).strip()


def test_test_job_is_version_by_two_shards() -> None:
    job = _jobs()["test"]
    assert job["strategy"]["matrix"] == {"python-version": ["3.11", "3.12", "3.13", "3.14"], "shard": [1, 2]}
    run = _step(job, "uv run pytest")["run"]
    assert (_option(run, "--splits"), _option(run, "--group")) == ("2", "${{matrix.shard}}")
    assert _option(run, "--durations-path") == f"{DURATIONS}/suite.json"
    assert _option(run, "--deselect") == CONFORMANCE_CASES


def test_checks_run_in_the_first_shard_only() -> None:
    job = _jobs()["test"]
    for command in ("../scripts/sync-shared --check", "uv run ruff", "uv run basedpyright"):
        assert _condition(_step(job, command)) == "matrix.shard == 1", command
    for command in ("uv sync", "uv run pytest"):
        assert _condition(_step(job, command)) is None, command


def test_cross_twin_job_is_twin_by_three_shards() -> None:
    job = _jobs()["cross-twin"]
    assert job["strategy"]["matrix"] == {"twin": ["python", "typescript"], "shard": [1, 2, 3]}
    run = _step(job, "scripts/conformance-cross")["run"]
    assert _normal(run).split()[1:3] == ["--twin", "${{matrix.twin}}"]
    assert (_option(run, "--splits"), _option(run, "--group")) == ("3", "${{matrix.shard}}")
    assert _option(run, "--durations-path") == f"{DURATIONS}/cross-${{{{matrix.twin}}}}.json"


def _collect(env: dict[str, str], args: list[str]) -> list[str]:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "-n", "0", "-p", "no:cacheprovider", *args],
        cwd=PROJECT_ROOT, env=env, capture_output=True, text=True, timeout=600, check=False,
    )
    assert proc.returncode == 0, proc.stdout[-3000:] + proc.stderr[-3000:]
    return [line for line in proc.stdout.splitlines() if "::" in line]


@pytest.mark.parametrize("kind", KINDS)
def test_each_shard_split_partitions_its_job(kind: str, tmp_path: Path) -> None:
    shards, extra, args = KINDS[kind]
    durations = PROJECT_ROOT / DURATIONS / f"{kind}.json"
    assert durations.is_file()
    env = {k: v for k, v in os.environ.items() if not k.startswith(("LA_", "PYTEST_"))} | extra
    if extra:
        env["LA_NODE_BIN_DIR"] = str(tmp_path)  # collection needs only the key
    full = _collect(env, args)
    groups = [
        _collect(env, [*args, "--splits", str(shards), "--group", str(g), "--durations-path", str(durations)])
        for g in range(1, shards + 1)
    ]
    assert full
    assert sorted(node for group in groups for node in group) == sorted(full)
    stored = json.loads(durations.read_text(encoding="utf-8"))
    assert isinstance(stored, dict)
    assert set(stored) & set(full)
    assert all(isinstance(seconds, int | float) and seconds > 0 for seconds in stored.values())
