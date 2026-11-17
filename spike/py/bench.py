"""Times dr's per-file analysis end to end over a file list: decode, parse, analyse, with phase timers; no dump.

Usage: bench.py --root DIR --regime keep|drop < files. Prints one JSON object of seconds.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from living_architecture.refactor.bindings import _module_parts, _Parsed
from living_architecture.refactor.python_project import Snapshot
from living_architecture.refactor.python_source import SourceFile


def run(root: Path, rels: list[str], *, keep: bool) -> dict[str, object]:
    """Each file decoded, parsed and analysed; analysed states kept when `keep`, as `World` keeps them."""
    snapshot = Snapshot(root)
    kept: list[_Parsed] = []
    decode = parse = analyse = 0.0
    analysed = 0
    start = time.perf_counter()
    for rel in rels:
        t0 = time.perf_counter()
        try:
            text = snapshot.text(rel)
        except (UnicodeDecodeError, LookupError):
            decode += time.perf_counter() - t0
            continue
        t1 = time.perf_counter()
        source = SourceFile(root / rel, text)
        t2 = time.perf_counter()
        if source.tree is not None:
            parts, is_package = _module_parts([""], rel)
            parsed = _Parsed(source, source.tree, parts, is_package)
            analysed += 1
            if keep:
                kept.append(parsed)
        t3 = time.perf_counter()
        decode, parse, analyse = decode + t1 - t0, parse + t2 - t1, analyse + t3 - t2
    total = time.perf_counter() - start
    return {"files": len(rels), "analysed": analysed, "kept": len(kept), "total": total, "decode": decode,
            "parse": parse, "analyse": analyse}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--regime", choices=("keep", "drop"), required=True)
    args = parser.parse_args(argv)
    rels = [line.rstrip("\n") for line in sys.stdin if line.strip()]
    print(json.dumps(run(args.root, rels, keep=args.regime == "keep")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
