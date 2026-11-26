"""The sharded CI jobs: the workflow's shape and the partition each shard split makes."""

import json
import os
import re
import shlex
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest
import yaml

REPO_ROOT = next(p for p in Path(__file__).resolve().parents if (p / "shared").is_dir() and (p / "plugin").is_dir())
CI = REPO_ROOT / ".github" / "workflows" / "ci.yml"
PACKAGES = ("trmv", "la")
DURATIONS = "tests/durations"
CONFORMANCE_CASES = "tests/test_conformance.py::test_case"
UV_RUN = "uv run --locked --no-build"
# Per package: the tests its cross-twin run collects, as node/scripts/conformance.mjs runs them.
CROSS_TESTS = {"trmv": ["tests/test_conformance.py", "tests/test_module_map_equivalence.py"], "la": ["tests/test_conformance.py"]}
# Per job kind: shard count, environment and pytest arguments, as the CI job runs them in a package.
KINDS = {
    "suite": (2, {}, lambda package: ["--deselect", CONFORMANCE_CASES]),
    "cross-python": (3, {"LA_CONFORMANCE_CROSS": "1", "LA_CONFORMANCE_TWIN": "python"}, CROSS_TESTS.__getitem__),
    "cross-typescript": (3, {"LA_CONFORMANCE_CROSS": "1", "LA_CONFORMANCE_TWIN": "typescript"},
                         CROSS_TESTS.__getitem__),
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


def test_test_job_is_version_by_package_by_two_shards() -> None:
    job = _jobs()["test"]
    assert job["strategy"]["matrix"] == {
        "python-version": ["3.11", "3.12", "3.13", "3.14"], "package": list(PACKAGES), "shard": [1, 2]
    }
    assert _normal(job["defaults"]["run"]["working-directory"]) == "python/${{matrix.package}}"
    run = _step(job, f"{UV_RUN} pytest")["run"]
    assert (_option(run, "--splits"), _option(run, "--group")) == ("2", "${{matrix.shard}}")
    assert _option(run, "--durations-path") == f"{DURATIONS}/suite.json"
    assert _option(run, "--deselect") == CONFORMANCE_CASES


def test_checks_run_in_the_first_shard_only() -> None:
    job = _jobs()["test"]
    for command in ("../../scripts/sync-shared --check", f"{UV_RUN} ruff", f"{UV_RUN} basedpyright"):
        assert _condition(_step(job, command)) == "matrix.shard == 1", command
    for command in ("uv sync", f"{UV_RUN} pytest"):
        assert _condition(_step(job, command)) is None, command


def test_uv_steps_install_only_locked_prebuilt_dependencies() -> None:
    runs = [_normal(step.get("run", "")).split() for job in _jobs().values() for step in job["steps"]]
    uv = [tokens for tokens in runs if tokens[:2] in (["uv", "sync"], ["uv", "run"])]
    assert len(uv) == 7
    assert all("--locked" in tokens and "--no-build" in tokens for tokens in uv), uv


@pytest.mark.parametrize("package", PACKAGES)
def test_idle_workers_steal_queued_tests(package: str) -> None:
    # A shard's expensive tests sit together in collection order; without stealing, one worker runs them all.
    pyproject = REPO_ROOT / "python" / package / "pyproject.toml"
    pytest_options = tomllib.loads(pyproject.read_text(encoding="utf-8"))["tool"]["pytest"]
    addopts = shlex.split(pytest_options["ini_options"]["addopts"])
    assert addopts[addopts.index("--dist") + 1] == "worksteal"


def test_cross_twin_job_is_twin_by_three_shards() -> None:
    job = _jobs()["cross-twin"]
    assert job["strategy"]["matrix"] == {"twin": ["python", "typescript"], "shard": [1, 2, 3]}
    run = _step(job, "scripts/conformance-cross")["run"]
    assert _normal(run).split()[1:3] == ["--twin", "${{matrix.twin}}"]
    assert (_option(run, "--splits"), _option(run, "--group")) == ("3", "${{matrix.shard}}")
    assert _option(run, "--durations-path") == f"{DURATIONS}/cross-${{{{matrix.twin}}}}.json"


def _collect(project: Path, env: dict[str, str], args: list[str]) -> list[str]:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "-n", "0", "-p", "no:cacheprovider", *args],
        cwd=project, env=env, capture_output=True, text=True, timeout=600, check=False,
    )
    assert proc.returncode == 0, proc.stdout[-3000:] + proc.stderr[-3000:]
    return [line for line in proc.stdout.splitlines() if "::" in line]


@pytest.mark.parametrize("package", PACKAGES)
@pytest.mark.parametrize("kind", KINDS)
def test_each_shard_split_partitions_its_job(kind: str, package: str, tmp_path: Path) -> None:
    shards, extra, package_args = KINDS[kind]
    args = package_args(package)
    project = REPO_ROOT / "python" / package
    durations = project / DURATIONS / f"{kind}.json"
    assert durations.is_file()
    env = {k: v for k, v in os.environ.items() if not k.startswith(("LA_", "PYTEST_"))} | extra
    if extra:
        env["LA_NODE_BIN_DIR"] = str(tmp_path)  # collection needs only the key
    full = _collect(project, env, args)
    groups = [
        _collect(project, env, [*args, "--splits", str(shards), "--group", str(g), "--durations-path", str(durations)])
        for g in range(1, shards + 1)
    ]
    assert full
    assert sorted(node for group in groups for node in group) == sorted(full)
    stored = json.loads(durations.read_text(encoding="utf-8"))
    assert isinstance(stored, dict)
    assert set(stored) & set(full)
    assert all(isinstance(seconds, int | float) and seconds > 0 for seconds in stored.values())
