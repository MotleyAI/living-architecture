"""The parser-fidelity measurement: CPython's and ruff's span dumps over the synthetic set, the conformance fixtures and
the SLayer copy on CPython 3.11 to 3.14, as one JSON report: the difference classes (count, example and the example
file's special forms), the accept/reject table, dr's decoding rule against `tokenize.detect_encoding`, and the files
whose CPython dumps differ between versions.

Usage: fidelity_run.py --slayer DIR [--out FILE]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

from corpus import CONFORMANCE, DATA, REPO, SPIKE, check_manifest, py_files
from fidelity_compare import compare_files, tally
from fidelity_dump import encodings

VERSIONS = ("3.11", "3.12", "3.13", "3.14")
TARGET = SPIKE / "rust" / "target" / "release"
Json = dict[str, object]


def _lines(stdout: str) -> dict[str, Json]:
    pairs = (line.split("\t", 1) for line in stdout.splitlines() if "\t" in line)
    return {rel: json.loads(text) for rel, text in pairs}


def python_dumps(script: str, version: str, root: Path, files: list[str]) -> dict[str, Json]:
    command = ["uv", "run", "-q", "--isolated", "--no-project", "--python", version, "--with-editable",
               str(REPO / "python"), "python", str(SPIKE / "py" / script), "--root", str(root)]
    return _lines(subprocess.run(command, input="\n".join(files), capture_output=True, text=True, check=True).stdout)


def rust_dumps(version: str, root: Path, files: list[str]) -> dict[str, Json]:
    command = [str(TARGET / "fidelity-dump"), "--python-version", version, "--root", str(root)]
    return _lines(subprocess.run(command, input="\n".join(files), capture_output=True, text=True, check=True).stdout)


def forms(data: bytes) -> list[str]:
    """The special forms a file's bytes hold."""
    found = []
    if data.startswith(b"\xef\xbb\xbf"):
        found.append("bom")
    if b"\r\n" in data:
        found.append("crlf")
    if b"\r" in data.replace(b"\r\n", b""):
        found.append("lone-cr")
    if b"\x0c" in data:
        found.append("form-feed")
    if any(b"coding" in line for line in data.split(b"\n", 2)[:2]):
        found.append("cookie")
    if not data.isascii():
        found.append("non-ascii")
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--slayer", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)
    slayer = args.slayer.resolve()
    check_manifest(slayer)
    subprocess.run(["cargo", "build", "--release", "--manifest-path", str(SPIKE / "rust" / "Cargo.toml")], check=True,
                   capture_output=True)
    corpora = {"data": DATA, "conformance": CONFORMANCE, "slayer": slayer}
    report: Json = {"options": {}, "classes": {}, "accept_reject": {}, "cpython_cross_version": {}, "encodings": {}}
    for name, root in corpora.items():
        files = py_files(root)
        report["encodings"][name] = {rel: e for rel in files if (e := encodings((root / rel).read_bytes()))["differ"]}  # type: ignore[index]
        python_by_version: dict[str, dict[str, Json]] = {}
        binding_by_version: dict[str, dict[str, Json]] = {}
        for version in VERSIONS:
            python = python_dumps("fidelity_dump.py", version, root, files)
            python_by_version[version] = python
            binding_by_version[version] = python_dumps("binding_dump.py", version, root, files)
            rust = rust_dumps(version, root, files)
            rows = tally(compare_files(python, rust))
            for row in rows:
                example = row["example"]
                example["forms"] = forms((root / example["path"]).read_bytes())  # type: ignore[index]
            report["classes"][f"{name}@{version}"] = rows  # type: ignore[index]
            pairs = Counter((python[rel]["status"], rust[rel]["status"]) for rel in files)
            examples = {f"{p} / {r}": next(rel for rel in files if (python[rel]["status"], rust[rel]["status"]) == (p, r))
                        for p, r in pairs if p != r}
            report["accept_reject"][f"{name}@{version}"] = {  # type: ignore[index]
                "counts": {f"{p} / {r}": n for (p, r), n in sorted(pairs.items())}, "examples": examples}
        cross: Json = {}
        for label, dumps in (("fidelity", python_by_version), ("binding", binding_by_version)):
            differing = []
            for rel in files:
                seen = {json.dumps(dumps[v][rel], sort_keys=True) for v in VERSIONS if dumps[v][rel]["status"] == "ok"}
                if len(seen) > 1:
                    differing.append(rel)
            cross[label] = differing
        report["cpython_cross_version"][name] = cross  # type: ignore[index]
    for version in VERSIONS:
        done = subprocess.run([str(TARGET / "fidelity-dump"), "--describe-options", "--python-version", version],
                              capture_output=True, text=True, check=True)
        report["options"][version] = done.stdout.strip()  # type: ignore[index]
    text = json.dumps(report, indent=1, ensure_ascii=False)
    if args.out is not None:
        args.out.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
