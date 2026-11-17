"""Compares CPython's and ruff's span dumps of the same file, and tallies the differences by class.

Usage: fidelity_compare.py PYTHON_DUMPS RUST_DUMPS; each file holds `REL<TAB>JSON` lines. Prints the class table as JSON.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from binding_dump import canonical

Json = dict[str, object]
SECTIONS = ("tokens", "nodes", "strings")


def _key(entry: Json) -> str:
    return canonical(entry)


def _pair(python: Json, rust: Json) -> str | None:
    """How a CPython-only and a ruff-only entry of the same kind differ, if they are one entry seen two ways."""
    if python["chars"] == rust["chars"]:
        return "bytes" if python["bytes"] != rust["bytes"] else "node"
    if python["chars"][0] == rust["chars"][0]:  # type: ignore[index]
        return "end"
    if python["chars"][1] == rust["chars"][1]:  # type: ignore[index]
        return "start"
    return None


def _cost(python: Json, rust: Json) -> tuple[int, int] | None:
    """How far apart two entries of one kind are: same span first, then a shared boundary and the nearest other one."""
    if python["kind"] != rust["kind"] or _pair(python, rust) is None:
        return None
    (ps, pe), (rs, re) = python["chars"], rust["chars"]  # type: ignore[misc]
    return (0, 0) if (ps, pe) == (rs, re) else (1, abs(pe - re) if ps == rs else abs(ps - rs))


def _section(name: str, python: list[Json], rust: list[Json]) -> list[Json]:
    left = Counter(_key(e) for e in python)
    right = Counter(_key(e) for e in rust)
    only_python = [json.loads(k) for k in sorted((left - right).elements())]
    only_rust = [json.loads(k) for k in sorted((right - left).elements())]
    candidates = sorted((cost, i, j) for i, p in enumerate(only_python) for j, r in enumerate(only_rust)
                        if (cost := _cost(p, r)) is not None)
    matched: dict[int, int] = {}
    taken: set[int] = set()
    for _, i, j in candidates:
        if i not in matched and j not in taken:
            matched[i] = j
            taken.add(j)
    found: list[Json] = []
    for i, entry in enumerate(only_python):
        if i in matched:
            match = only_rust[matched[i]]
            found.append({"section": name, "kind": entry["kind"], "class": _pair(entry, match), "python": entry, "rust": match})
        else:
            found.append({"section": name, "kind": entry["kind"], "class": "python-only", "python": entry, "rust": None})
    found += [{"section": name, "kind": e["kind"], "class": "rust-only", "python": None, "rust": e}
              for j, e in enumerate(only_rust) if j not in taken]
    return found


def compare(python: Json, rust: Json) -> list[Json]:
    """The differences between two dumps of one file; empty when they are equal."""
    if python["status"] != rust["status"]:
        return [{"section": "status", "kind": None, "class": f"{python['status']} vs {rust['status']}",
                 "python": python["status"], "rust": rust["status"]}]
    found: list[Json] = []
    for name in SECTIONS:
        left, right = python.get(name), rust.get(name)
        if isinstance(left, str) or isinstance(right, str):
            if left != right:
                found.append({"section": name, "kind": None, "class": "tokenizer error", "python": left, "rust": right})
            continue
        found += _section(name, left or [], right or [])  # type: ignore[arg-type]
    return found


def tally(results: dict[str, list[Json]]) -> list[Json]:
    """Per difference class (section, kind, class): its count and the first example by path."""
    table: dict[tuple[str, str, str], Json] = {}
    for rel in sorted(results):
        for diff in results[rel]:
            key = (str(diff["section"]), str(diff["kind"]), str(diff["class"]))
            row = table.setdefault(key, {"section": key[0], "kind": diff["kind"], "class": key[2], "count": 0,
                                         "example": {"path": rel, "python": diff["python"], "rust": diff["rust"]}})
            row["count"] = int(row["count"]) + 1  # type: ignore[call-overload]
    return [table[k] for k in sorted(table)]


def compare_files(python: dict[str, Json], rust: dict[str, Json]) -> dict[str, list[Json]]:
    """The differences per file, over the files either side dumped."""
    results: dict[str, list[Json]] = {}
    for rel in sorted(python.keys() | rust.keys()):
        if rel not in rust:
            results[rel] = [{"section": "file", "kind": None, "class": "missing-rust", "python": None, "rust": None}]
        elif rel not in python:
            results[rel] = [{"section": "file", "kind": None, "class": "rust-only-file", "python": None, "rust": None}]
        else:
            results[rel] = compare(python[rel], rust[rel])
    return results


def read_dumps(path: Path) -> dict[str, Json]:
    pairs = (line.rstrip("\n").split("\t", 1) for line in path.read_text(encoding="utf-8").splitlines() if line)
    return {rel: json.loads(text) for rel, text in pairs}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("python", type=Path)
    parser.add_argument("rust", type=Path)
    args = parser.parse_args(argv)
    python, rust = read_dumps(args.python), read_dumps(args.rust)
    sys.stdout.write(json.dumps(tally(compare_files(python, rust)), indent=1, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
