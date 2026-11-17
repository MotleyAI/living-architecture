"""The baseline the port is weighed against: the issue's single-method rename on the SLayer copy with dr at this
checkout's HEAD, dry run, cold (`LA_CACHE_DIR` empty each run), unprofiled runs (median of phases and peak RSS) plus
one diagnostic cProfile run. Prints one JSON report.

Usage: baseline_run.py --slayer DIR [--runs 3] [--out FILE]
"""

from __future__ import annotations

import argparse
import json
import os
import pstats
import re
import statistics
import subprocess
import sys
import tempfile
from pathlib import Path

from corpus import REPO, check_manifest

RENAME = ["rename", "--file", "slayer/storage/base.py", "--symbol", "StorageBackend.validate_for_save", "--new-name",
          "validate_before_save", "--allow-blindspots"]
VENV = REPO / "python" / ".venv" / "bin"


def _phases(stderr: str) -> dict[str, float]:
    """`--timings`' `timing: PHASE SECONDSs` lines by phase."""
    found: dict[str, float] = {}
    for line in stderr.splitlines():
        m = re.fullmatch(r"timing: (\S+) ([\d.]+)s", line.strip())
        if m:
            found[m.group(1).strip()] = float(m.group(2))
    return found


def run_once(slayer: Path, profile: Path | None = None) -> dict[str, object]:
    with tempfile.TemporaryDirectory() as cache:
        env = {**os.environ, "LA_CACHE_DIR": cache}
        script = str(VENV / "dr-refactor")
        command = [str(VENV / "python"), "-m", "cProfile", "-o", str(profile), script] if profile is not None else [script]
        done = subprocess.run(["/usr/bin/time", "-v", *command, "--timings", *RENAME], cwd=slayer, env=env,
                              capture_output=True, text=True, check=False)
    peak = re.search(r"Maximum resident set size \(kbytes\): (\d+)", done.stderr)
    wall = re.search(r"Elapsed \(wall clock\) time \(h:mm:ss or m:ss\): ([\d:.]+)", done.stderr)
    return {"exit": done.returncode, "phases": _phases(done.stderr.split("\tCommand being timed")[0]),
            "peak_rss_mb": round(int(peak.group(1)) / 1024, 1) if peak else None,
            "wall": wall.group(1) if wall else None, "stdout_lines": len(done.stdout.splitlines())}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--slayer", type=Path, required=True)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)
    slayer = args.slayer.resolve()
    check_manifest(slayer)
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True, check=True).stdout.strip()
    runs = [run_once(slayer) for _ in range(args.runs)]
    names = sorted({k for r in runs for k in r["phases"]})  # type: ignore[attr-defined]
    medians = {n: statistics.median(r["phases"][n] for r in runs if n in r["phases"]) for n in names}  # type: ignore[index,operator]
    with tempfile.TemporaryDirectory() as where:
        profile = Path(where) / "rename.prof"
        profiled = run_once(slayer, profile)
        stats = pstats.Stats(str(profile))
        top = sorted(stats.stats.items(), key=lambda kv: kv[1][3], reverse=True)[:25]  # type: ignore[attr-defined]
        profiled["top_cumulative"] = [f"{fn[0].rsplit('/', 1)[-1]}:{fn[1]}({fn[2]}) {v[3]:.2f}s cum, {v[1]} calls"
                                      for fn, v in top]
    report = {"head": head, "command": ["dr-refactor", "--timings", *RENAME], "runs": runs, "phase_medians": medians,
              "peak_rss_mb_median": statistics.median(r["peak_rss_mb"] for r in runs),  # type: ignore[type-var]
              "profiled_diagnostic_only": profiled}
    text = json.dumps(report, indent=1)
    if args.out is not None:
        args.out.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
