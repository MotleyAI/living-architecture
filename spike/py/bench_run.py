"""The speedup measurement over the SLayer copy: refuses a changed corpus, runs the binding differential on CPython
3.11 to 3.14, then times both sides on the matching files and on all files. Prints one JSON report.

Usage: bench_run.py --slayer DIR [--runs 5] [--out FILE]
"""

from __future__ import annotations

import argparse
import json
import math
import os
import platform
import re
import statistics
import subprocess
import sys
import tempfile
from pathlib import Path

from corpus import REPO, SPIKE, check_manifest, py_files

VERSIONS = ("3.11", "3.12", "3.13", "3.14")
BENCH_PYTHON = "3.12"
TARGET = SPIKE / "rust" / "target" / "release"


def _uv_python(version: str) -> list[str]:
    return ["uv", "run", "-q", "--isolated", "--no-project", "--python", version, "--with-editable", str(REPO / "python"),
            "python"]


def _lines(stdout: str) -> dict[str, str]:
    return dict(line.split("\t", 1) for line in stdout.splitlines() if "\t" in line)


def differential(root: Path, files: list[str]) -> dict[str, object]:
    """Each file's binding dumps on both sides under every version; the files matching wherever CPython accepts."""
    feed = "\n".join(files)
    python: dict[str, dict[str, str]] = {}
    rust: dict[str, dict[str, str]] = {}
    for v in VERSIONS:
        done = subprocess.run([*_uv_python(v), str(SPIKE / "py" / "binding_dump.py"), "--root", str(root)], input=feed,
                              capture_output=True, text=True, check=True)
        python[v] = _lines(done.stdout)
        done = subprocess.run([str(TARGET / "binding-dump"), "--python-version", v, "--root", str(root)], input=feed,
                              capture_output=True, text=True, check=True)
        rust[v] = _lines(done.stdout)
    matching, mismatched, rejected, cross_version = [], [], [], []
    for rel in files:
        accepting = [v for v in VERSIONS if json.loads(python[v][rel])["status"] != "syntax-error"]
        if not accepting:
            rejected.append(rel)
        elif all(rust[v].get(rel) == python[v][rel] for v in accepting):
            matching.append(rel)
        else:
            mismatched.append({"path": rel, "versions": [v for v in accepting if rust[v].get(rel) != python[v][rel]]})
        if len({python[v][rel] for v in accepting}) > 1:
            cross_version.append(rel)
    return {"files": len(files), "matching": matching, "mismatched": mismatched, "rejected_everywhere": rejected,
            "cpython_cross_version": cross_version}


def _peak_kb(stderr: str) -> int:
    found = re.search(r"Maximum resident set size \(kbytes\): (\d+)", stderr)
    return int(found.group(1)) if found else -1


def _timed(command: list[str], files: list[str]) -> dict[str, object]:
    done = subprocess.run(["/usr/bin/time", "-v", *command], input="\n".join(files), capture_output=True, text=True,
                          check=True)
    result = json.loads(done.stdout)
    result["peak_rss_mb"] = round(_peak_kb(done.stderr) / 1024, 1)
    return result


def _stats(runs: list[dict[str, object]]) -> dict[str, object]:
    """Median and nearest-rank p95 of each timed field over the runs."""
    out: dict[str, object] = {"runs": len(runs)}
    for key in ("total", "decode", "parse", "analyse", "peak_rss_mb"):
        values = sorted(float(r[key]) for r in runs if key in r)  # type: ignore[arg-type]
        if values:
            out[key] = {"median": statistics.median(values), "p95": values[math.ceil(0.95 * len(values)) - 1]}
    out["analysed"] = runs[0]["analysed"]
    return out


def venv(where: Path) -> str:
    """A CPython `BENCH_PYTHON` venv in `where` with dr installed from this checkout; its interpreter."""
    subprocess.run(["uv", "venv", "-q", "--python", BENCH_PYTHON, str(where)], check=True)
    interpreter = str(where / "bin" / "python")
    subprocess.run(["uv", "pip", "install", "-q", "--python", interpreter, "-e", str(REPO / "python")], check=True)
    return interpreter


def bench(interpreter: str, root: Path, files: list[str], runs: int) -> dict[str, object]:
    """Both sides on `files`, single-threaded in both lifetime regimes, and the Rust side on rayon."""
    rows: dict[str, object] = {}
    for regime in ("keep", "drop"):
        python = [_timed([interpreter, str(SPIKE / "py" / "bench.py"), "--root", str(root), "--regime", regime], files)
                  for _ in range(runs)]
        rust = [_timed([str(TARGET / "binding-bench"), "--python-version", BENCH_PYTHON, "--root", str(root), "--regime",
                        regime], files) for _ in range(runs)]
        threads = os.cpu_count() or 1
        parallel = [_timed([str(TARGET / "binding-bench"), "--python-version", BENCH_PYTHON, "--root", str(root),
                            "--regime", regime, "--threads", str(threads)], files) for _ in range(runs)]
        python_s, rust_s, parallel_s = _stats(python), _stats(rust), _stats(parallel)
        rows[regime] = {"python": python_s, "rust": rust_s, f"rust_rayon_{threads}": parallel_s,
                        "speedup": _ratio(python_s, rust_s), "speedup_rayon": _ratio(python_s, parallel_s)}
    return rows


def _ratio(slow: dict[str, object], fast: dict[str, object]) -> float:
    return round(slow["total"]["median"] / fast["total"]["median"], 1)  # type: ignore[index]


def machine() -> dict[str, object]:
    def read(path: str) -> str:
        try:
            return Path(path).read_text(encoding="utf-8").strip()
        except OSError:
            return "unknown"

    model = next((line.split(":", 1)[1].strip() for line in read("/proc/cpuinfo").splitlines()
                  if line.startswith("model name")), "unknown")
    return {"cpu": model, "cpus": os.cpu_count(), "governor": read("/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor"),
            "loadavg": read("/proc/loadavg"), "kernel": platform.release()}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--slayer", type=Path, required=True)
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)
    root = args.slayer.resolve()
    check_manifest(root)
    subprocess.run(["cargo", "build", "--release", "--manifest-path", str(SPIKE / "rust" / "Cargo.toml")], check=True,
                   capture_output=True)
    files = py_files(root)
    diff = differential(root, files)
    for rel in files:  # warm-up: both sides then read the files from the page cache
        (root / rel).read_bytes()
    report = {"machine_before": machine(), "differential": {k: (len(v) if isinstance(v, list) and k == "matching" else v)
                                                            for k, v in diff.items()}}
    with tempfile.TemporaryDirectory() as where:
        interpreter = venv(Path(where))
        report["matching_files"] = bench(interpreter, root, diff["matching"], args.runs)  # type: ignore[arg-type]
        report["all_files"] = (bench(interpreter, root, files, args.runs) if len(diff["matching"]) != len(files)  # type: ignore[arg-type]
                               else "same as matching_files")
    report["machine_after"] = machine()
    text = json.dumps(report, indent=1)
    if args.out is not None:
        args.out.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
