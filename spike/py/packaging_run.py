"""The packaging measurement: console-script start-up against a plain binary and a pure-Python script, and the
abi3 wheel built for the four Linux targets, each loaded where this machine can run it. Prints one JSON report.

Usage: packaging_run.py [--out FILE]
"""

from __future__ import annotations

import argparse
import json
import math
import platform
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from corpus import SPIKE

HELLO = SPIKE / "rust" / "hello"
PYTHON = "3.12"
WARMUP, TIMED = 10, 50
TARGETS = {  # target triple: (zig, docker image that loads it, or None)
    "x86_64-unknown-linux-gnu": (False, None),
    "x86_64-unknown-linux-musl": (True, "python:3.12-alpine"),
    "aarch64-unknown-linux-gnu": (True, None),
    "aarch64-unknown-linux-musl": (True, None),
}
PURE = """[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "py-hello"
version = "0.0.0"

[project.scripts]
py-hello = "py_hello:main"
"""


def build(out: Path, target: str, *, zig: bool) -> tuple[Path | None, str]:
    command = ["uvx", *(["--with", "ziglang"] if zig else []), "maturin", "build", "--release", "--manifest-path", str(HELLO / "Cargo.toml"), "--out", str(out),
               "--target", target, *(["--zig"] if zig else [])]
    done = subprocess.run(command, capture_output=True, text=True, check=False)
    found = sorted(out.glob("*.whl"))
    return (found[0] if done.returncode == 0 and found else None), done.stderr[-1500:]


def timed(command: list[str]) -> dict[str, float]:
    """Median and nearest-rank p95 wall time, in ms, of `TIMED` runs after `WARMUP` untimed ones."""
    for _ in range(WARMUP):
        subprocess.run(command, capture_output=True, check=True)
    samples = []
    for _ in range(TIMED):
        start = time.perf_counter()
        subprocess.run(command, capture_output=True, check=True)
        samples.append((time.perf_counter() - start) * 1000)
    samples.sort()
    return {"median_ms": round(statistics.median(samples), 2), "p95_ms": round(samples[math.ceil(0.95 * TIMED) - 1], 2)}


def startup(wheel: Path, where: Path) -> dict[str, object]:
    venv = where / "venv"
    subprocess.run(["uv", "venv", "-q", "--python", PYTHON, str(venv)], check=True)
    python = str(venv / "bin" / "python")
    pure = where / "pure"
    (pure / "py_hello").mkdir(parents=True)
    (pure / "pyproject.toml").write_text(PURE, encoding="utf-8")
    line = subprocess.run([str(SPIKE / "rust" / "target" / "release" / "dr-hello-plain")], capture_output=True, text=True,
                          check=True).stdout
    (pure / "py_hello" / "__init__.py").write_text(f"def main() -> None:\n    print({line.strip()!r})\n", encoding="utf-8")
    subprocess.run(["uv", "pip", "install", "-q", "--python", python, str(wheel), str(pure)], check=True)
    commands = {"console script (abi3 module)": [str(venv / "bin" / "dr-hello")],
                "plain Rust binary": [str(SPIKE / "rust" / "target" / "release" / "dr-hello-plain")],
                "pure-Python console script": [str(venv / "bin" / "py-hello")]}
    outputs = {name: subprocess.run(c, capture_output=True, text=True, check=True).stdout for name, c in commands.items()}
    assert len(set(outputs.values())) == 1, outputs
    return {"python": PYTHON, "warmup": WARMUP, "timed": TIMED, **{name: timed(c) for name, c in commands.items()}}


def load_in_docker(wheel: Path, image: str) -> dict[str, object]:
    script = (f"pip install -q --root-user-action=ignore /w/{wheel.name} && python -c 'import dr_hello; print(dr_hello.greeting())' "
              "&& dr-hello && dr-hello-two")
    done = subprocess.run(["docker", "run", "--rm", "-v", f"{wheel.parent}:/w:ro", image, "sh", "-c", script],
                          capture_output=True, text=True, check=False)
    return {"image": image, "exit": done.returncode, "stdout": done.stdout.strip().splitlines(), "stderr": done.stderr[-800:]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)
    subprocess.run(["rustup", "target", "add", *TARGETS], check=True, capture_output=True)
    subprocess.run(["cargo", "build", "--release", "--manifest-path", str(SPIKE / "rust" / "Cargo.toml"), "-p", "hello",
                    "--bin", "dr-hello-plain"], check=True, capture_output=True)
    report: dict[str, object] = {"machine": platform.machine(), "targets": {}, "macos": "not built (moved to DEV-2332)"}
    with tempfile.TemporaryDirectory() as tmp:
        where = Path(tmp)
        for target, (zig, image) in TARGETS.items():
            out = where / target
            wheel, error = build(out, target, zig=zig)
            row: dict[str, object] = {"zig": zig, "wheel": wheel.name if wheel else None,
                                      "size_kb": round(wheel.stat().st_size / 1024, 1) if wheel else None}
            if wheel is None:
                row["error"] = error
            elif target.startswith(platform.machine()) and image is None:
                row["loaded"] = "natively (see start-up)"
                report["startup"] = startup(wheel, where / "startup")
            elif image is not None:
                row["loaded"] = load_in_docker(wheel, image)
            else:
                row["loaded"] = "not loaded: this machine cannot run the target"
            report["targets"][target] = row  # type: ignore[index]
    text = json.dumps(report, indent=1)
    if args.out is not None:
        args.out.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
