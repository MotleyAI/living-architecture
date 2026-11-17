"""Canonical dump of dr's per-file binding analysis (`_Parsed` and its scopes), the oracle of the Rust port.

Usage: binding_dump.py --root DIR [REL ...]; with no REL, reads one per line from stdin. Prints `REL<TAB>JSON` per file.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from living_architecture.refactor.bindings import _module_parts, _Parsed
from living_architecture.refactor.python_project import Snapshot
from living_architecture.refactor.static_resolver import Binding, Scope

Json = dict[str, object]


def canonical(value: object) -> str:
    """The byte-exact JSON text both sides emit."""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _bindings(table: dict[str, list[Binding]]) -> list[list[object]]:
    return [[name, [list(b) if b is not None else None for b in found]] for name, found in sorted(table.items())]


def dump_parsed(parsed: _Parsed) -> Json:
    """Everything `_Parsed` and its scopes hold, scopes numbered in creation order."""
    ids = {id(s): i for i, s in enumerate(parsed.scopes)}

    def sid(scope: Scope | None) -> int | None:
        return None if scope is None else ids[id(scope)]

    named = parsed._named
    used = sorted({(sid(o.scope), name) for name, occs in named.items() for o in occs})
    by_id = parsed.scopes
    classes = sorted((sid(scope), name) for scope, name in parsed.points if scope.kind == "class")
    offsets = sorted({(name, o.offset) for name, occs in named.items() for o in occs})
    return {
        "status": "ok",
        "scopes": [
            {"id": i, "kind": s.kind, "parent": sid(s.parent), "raw": _bindings(s.raw), "bindings": _bindings(s.bindings),
             "globals": sorted(s.globals), "nonlocals": sorted(s.nonlocals)}
            for i, s in enumerate(by_id)
        ],
        "sites": sorted([sid(scope), name, offsets] for (scope, name), offsets in parsed.sites.items()),
        "points": sorted(
            [sid(scope), name, [[b, run, list(first) if first is not None else None] for b, run, first in found]]
            for (scope, name), found in parsed.points.items()
        ),
        "occurrences": [[name, [[o.offset, sid(o.scope), o.binds] for o in named[name]]] for name in sorted(named)],
        "stars": [[dotted, offset] for dotted, offset in parsed.stars],
        "all_names": sorted(parsed.all_names) if parsed.all_names is not None else None,
        "loops": sorted([sid(scope), [[list(span) for span in loop] for loop in loops]] for scope, loops in parsed.loops.items()),
        "resolution": [
            [i, name, sid(by_id[i].owner(name)), sid(by_id[i].resolving(name))] for i, name in used if i is not None
        ],
        "may_precede": [
            [c, name, at, parsed.may_precede(by_id[c], name, at)]
            for c, name in classes if c is not None
            for spelled, at in offsets if spelled == name
        ],
        "joined": [[i, [sid(j) for j in parsed.joined(s)]] for i, s in enumerate(by_id)],
    }


def analyse(snapshot: Snapshot, rel: str) -> _Parsed | Json:
    """`rel` decoded and parsed as dr does, analysed; the status dump when it does not decode or parse."""
    try:
        source = snapshot.source(rel)
    except (UnicodeDecodeError, LookupError):
        return {"status": "undecodable"}
    if source.tree is None:
        return {"status": "syntax-error"}
    parts, is_package = _module_parts([""], rel)
    return _Parsed(source, source.tree, parts, is_package)


def dump(root: Path, rel: str) -> Json:
    found = analyse(Snapshot(root), rel)
    return found if isinstance(found, dict) else dump_parsed(found)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("rels", nargs="*")
    args = parser.parse_args(argv)
    rels = args.rels or [line.rstrip("\n") for line in sys.stdin if line.strip()]
    out = sys.stdout
    for rel in rels:
        out.write(f"{rel}\t{canonical(dump(args.root, rel))}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
