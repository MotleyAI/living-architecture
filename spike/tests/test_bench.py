"""The bench drivers analyse the same files on both sides, and the runner's differential reports the matching set."""

from __future__ import annotations

import json
import subprocess

from bench_run import differential
from conftest import TARGET, rust_build
from corpus import DATA, REPO, SPIKE, py_files


def test_both_drivers_analyse_the_same_files() -> None:
    assert rust_build() is None
    feed = "\n".join(py_files(DATA))
    python = subprocess.run(["uv", "run", "-q", "--isolated", "--no-project", "--python", "3.12", "--with-editable",
                             str(REPO / "python"), "python", str(SPIKE / "py" / "bench.py"), "--root", str(DATA),
                             "--regime", "keep"], input=feed, capture_output=True, text=True, check=True)
    rust = subprocess.run([str(TARGET / "binding-bench"), "--python-version", "3.12", "--root", str(DATA), "--regime",
                           "keep"], input=feed, capture_output=True, text=True, check=True)
    found = [json.loads(done.stdout) for done in (python, rust)]
    assert [(f["files"], f["analysed"], f["kept"]) for f in found] == [(25, 19, 19)] * 2
    assert all(f["total"] >= f["decode"] + f["parse"] + f["analyse"] - 1e-3 for f in found)


def test_differential_reports_the_matching_set() -> None:
    assert rust_build() is None
    found = differential(DATA, py_files(DATA))
    assert found["mismatched"] == []
    assert found["rejected_everywhere"] == ["syntax_error.py"]
    assert len(found["matching"]) + 1 == len(py_files(DATA))  # type: ignore[arg-type]
