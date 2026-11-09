"""The stand-in `gh` shared by the unit tests and the conformance runner."""

import json
import sys
from pathlib import Path

# First route whose tokens all appear in argv wins; a route serves its `responses` in call order, the last
# repeating (counts kept beside the routes file). `--jq`/`-q` filters are applied with the real jq. With
# FAKE_GH_LOG set, every call is logged with any --input payload.
SCRIPT = """\
import fcntl, json, os, subprocess, sys

argv = sys.argv[1:]
routes_path = os.environ["FAKE_GH_ROUTES"]
with open(routes_path) as fh:
    routes = json.load(fh)
if os.environ.get("FAKE_GH_LOG"):
    entry = {"argv": argv}
    if "--input" in argv:
        with open(argv[argv.index("--input") + 1]) as fh:
            entry["input"] = fh.read()
    with open(os.environ["FAKE_GH_LOG"], "a") as fh:
        fh.write(json.dumps(entry) + "\\n")
for index, route in enumerate(routes):
    if all(tok in argv for tok in route["match"]):
        with os.fdopen(os.open(routes_path + ".counts", os.O_RDWR | os.O_CREAT), "r+") as fh:
            fcntl.flock(fh, fcntl.LOCK_EX)
            counts = json.loads(fh.read() or "{}")
            served = counts.get(str(index), 0)
            counts[str(index)] = served + 1
            fh.seek(0)
            fh.truncate()
            fh.write(json.dumps(counts))
        response = route["responses"][min(served, len(route["responses"]) - 1)]
        out = response["stdout"]
        for flag in ("--jq", "-q"):
            if flag in argv:
                jq = subprocess.run(["jq", "-rc", argv[argv.index(flag) + 1]], input=out,
                                    capture_output=True, text=True, check=False)
                sys.stderr.write(jq.stderr)
                out = jq.stdout
        sys.stdout.write(out)
        sys.exit(response["exit"])
sys.stderr.write("fake gh: no route for " + " ".join(argv) + "\\n")
sys.exit(1)
"""


def _response(spec: dict) -> dict:
    stdout = spec.get("stdout", "")
    return {"stdout": stdout if isinstance(stdout, str) else json.dumps(stdout), "exit": spec.get("exit", 0)}


def write_routes(path: Path, specs: list[dict]) -> None:
    """Case-format routes (`match` with `stdout`/`exit`, or `responses`) as the fake reads them; resets counts."""
    routes = [{"match": s["match"], "responses": [_response(r) for r in s.get("responses") or [s]]} for s in specs]
    path.write_text(json.dumps(routes), encoding="utf-8")
    path.with_name(path.name + ".counts").unlink(missing_ok=True)


def install(bin_dir: Path) -> None:
    gh = bin_dir / "gh"
    gh.write_text(f"#!{sys.executable}\n{SCRIPT}", encoding="utf-8")
    gh.chmod(0o755)
