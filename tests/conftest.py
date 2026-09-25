import json
import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

from living_architecture.shims import SCRIPTS_DIR

# Stand-in `gh`: first route whose tokens all appear in argv wins; `--jq`/`-q`
# filters are applied with the real jq; every call is logged with any --input payload.
FAKE_GH = """\
import json, os, subprocess, sys

argv = sys.argv[1:]
with open(os.environ["FAKE_GH_ROUTES"]) as fh:
    routes = json.load(fh)
entry = {"argv": argv}
if "--input" in argv:
    with open(argv[argv.index("--input") + 1]) as fh:
        entry["input"] = fh.read()
with open(os.environ["FAKE_GH_LOG"], "a") as fh:
    fh.write(json.dumps(entry) + "\\n")
for route in routes:
    if all(tok in argv for tok in route["match"]):
        out = route.get("stdout", "")
        for flag in ("--jq", "-q"):
            if flag in argv:
                jq = subprocess.run(["jq", "-rc", argv[argv.index(flag) + 1]], input=out,
                                    capture_output=True, text=True, check=False)
                sys.stderr.write(jq.stderr)
                out = jq.stdout
        sys.stdout.write(out)
        sys.exit(route.get("exit", 0))
sys.stderr.write("fake gh: no route for " + " ".join(argv) + "\\n")
sys.exit(1)
"""


class FakeGh:
    def __init__(self, tmp_path: Path) -> None:
        self.bin = tmp_path / "fakebin"
        self.bin.mkdir()
        self.routes_file = tmp_path / "routes.json"
        self.log_file = tmp_path / "gh.log"
        self.tmp = tmp_path
        gh = self.bin / "gh"
        gh.write_text(f"#!{sys.executable}\n{FAKE_GH}")
        gh.chmod(0o755)
        self.route()

    def route(self, *routes: tuple[list[str], object] | tuple[list[str], object, int]) -> None:
        """Each route: (argv tokens, stdout as str or JSON-able, [exit code])."""
        out = []
        for r in routes:
            stdout = r[1] if isinstance(r[1], str) else json.dumps(r[1])
            out.append({"match": r[0], "stdout": stdout, "exit": r[2] if len(r) > 2 else 0})
        self.routes_file.write_text(json.dumps(out))

    def calls(self) -> list[dict]:
        if not self.log_file.exists():
            return []
        return [json.loads(line) for line in self.log_file.read_text().splitlines()]

    def env(self) -> dict[str, str]:
        return {
            **os.environ,
            "PATH": f"{self.bin}{os.pathsep}{os.environ['PATH']}",
            "FAKE_GH_ROUTES": str(self.routes_file),
            "FAKE_GH_LOG": str(self.log_file),
            "TMPDIR": str(self.tmp),
        }


@pytest.fixture
def fake_gh(tmp_path: Path) -> FakeGh:
    return FakeGh(tmp_path)


@pytest.fixture
def run_script(fake_gh: FakeGh) -> Callable[..., subprocess.CompletedProcess[str]]:
    def run(script: str, *args: str, stdin: str | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", str(SCRIPTS_DIR / script), *args],
            input=stdin if stdin is not None else "",
            capture_output=True,
            text=True,
            env=fake_gh.env(),
            cwd=fake_gh.tmp,
            check=False,
        )

    return run
