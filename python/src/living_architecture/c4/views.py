"""The constrained `views.c4` include grammar and view expansion over a root-local projection."""

from __future__ import annotations

import re
from pathlib import Path

from pydantic import BaseModel

from living_architecture.c4.index import read_index
from living_architecture.c4.model import ModelParse, Relation, project, roots, strip_line_comment
from living_architecture.contract import architecture, message


class Edge(BaseModel):
    src: str
    dst: str
    legacy: bool = False


class View(BaseModel):
    """A view of one language root; ids are local to the root."""

    id: str
    title: str
    root: str
    node_ids: list[str]
    edges: list[Edge]


class ViewsParse(BaseModel):
    views: list[View]
    findings: list[str]


class _RawView(BaseModel):
    """A view's include grammar, parsed before the depth knob is known."""

    id: str
    title: str
    root: str
    base: list[str]
    src_anchors: set[str]
    dst_anchors: set[str]


_TOKEN_RE = re.compile(r"'[^']*'|->|[\w.]+|\S")

DEFAULT_VIEW_DEPTH = 3

EMPTY_VIEWS = "views {\n}\n"


def _top(eid: str) -> str:
    return eid.split(".")[0]


def _level(eid: str) -> int:
    return eid.count(".") + 1


def _ancestor_at_level(eid: str, level: int) -> str:
    return ".".join(eid.split(".")[:level])


def _tokenize(text: str) -> list[tuple[str, str]]:
    stripped = "\n".join(strip_line_comment(line) for line in text.splitlines())
    tokens: list[tuple[str, str]] = []
    for m in _TOKEN_RE.finditer(stripped):
        tok = m.group(0)
        if tok.startswith("'"):
            tokens.append(("str", tok[1:-1]))
        elif tok == "->":
            tokens.append(("arrow", tok))
        elif tok == "*":
            tokens.append(("star", tok))
        elif tok in "{}(),":
            tokens.append((tok, tok))
        elif tok[0].isalnum() or tok[0] == "_":
            tokens.append(("word", tok))
        else:
            tokens.append(("unknown", tok))
    return tokens


class _Scope(BaseModel):
    """The root-local projection a view body is read against."""

    root: str
    model: ModelParse
    top_level: list[str]
    known: set[str]


def _scope(model: ModelParse, root: str) -> _Scope:
    local = project(model, root)
    return _Scope(
        root=root,
        model=local,
        top_level=[e.id for e in local.elements if e.parent is None],
        known={e.id for e in local.elements},
    )


class _Parser:
    """The include grammar over one token stream; findings accumulate in order."""

    def __init__(self, tokens: list[tuple[str, str]]) -> None:
        self.tokens = tokens
        self.pos = 0
        self.findings: list[str] = []

    def cur(self) -> tuple[str, str]:
        return self.tokens[self.pos] if self.pos < len(self.tokens) else ("eof", "")

    def advance(self) -> tuple[str, str]:
        tok = self.cur()
        self.pos += 1
        return tok

    def anchor_ok(self, scope: _Scope, name: str, form: str, findings: list[str]) -> bool:
        if name not in scope.known:
            findings.append(message("c4.include-unknown", form=form, name=name))
            return False
        if name not in scope.top_level:
            findings.append(message("c4.include-non-top-level", form=form, name=name))
            return False
        return True

    def read_spec(self, vid: str, scope: _Scope, raw: _RawView, findings: list[str]) -> None:  # NOSONAR(S3776) — one include production
        tok = self.advance()
        if tok[0] == "star":
            if self.cur()[0] == "arrow":
                self.advance()
                nxt = self.advance()
                if nxt[0] == "star":
                    findings.append(message("c4.star-to-star", view=vid))
                elif nxt[0] == "word":
                    if self.anchor_ok(scope, nxt[1], f"* -> {nxt[1]}", findings):
                        raw.dst_anchors.add(nxt[1])
                else:
                    findings.append(message("c4.malformed-predicate", view=vid))
            else:
                for eid in scope.top_level:
                    _add_base(raw, eid)
        elif tok[0] == "word":
            if self.cur()[0] == "arrow":
                self.advance()
                nxt = self.advance()
                if nxt[0] == "star":
                    if self.anchor_ok(scope, tok[1], f"{tok[1]} -> *", findings):
                        raw.src_anchors.add(tok[1])
                elif nxt[0] == "word":
                    findings.append(message("c4.unsupported-predicate", view=vid, src=tok[1], dst=nxt[1]))
                else:
                    findings.append(message("c4.malformed-predicate", view=vid))
            elif tok[1] not in scope.known:
                findings.append(message("c4.view-includes-unknown", view=vid, name=tok[1]))
            elif tok[1] not in scope.top_level:
                findings.append(message("c4.view-includes-non-top-level", view=vid, name=tok[1]))
            else:
                _add_base(raw, tok[1])
        else:
            findings.append(message("c4.unexpected-include-token", view=vid, token=tok[1]))

    def body(self, vid: str, scope: _Scope, findings: list[str]) -> _RawView:
        raw = _RawView(id=vid, title="", root=scope.root, base=[], src_anchors=set(), dst_anchors=set())
        while self.cur()[0] not in ("}", "eof"):
            tok = self.advance()
            if tok == ("word", "title"):
                st = self.advance()
                if st[0] == "str":
                    raw.title = st[1]
                else:
                    findings.append(message("c4.title-not-string", view=vid))
            elif tok == ("word", "include"):
                self.read_spec(vid, scope, raw, findings)
                while self.cur()[0] == ",":
                    self.advance()
                    self.read_spec(vid, scope, raw, findings)
            else:
                findings.append(message("c4.unrecognized-directive", view=vid, token=tok[1]))
        if self.cur()[0] == "}":
            self.advance()
        return raw

    def header(self) -> tuple[str, str | None] | None:
        """`view <id> [of <root>] {` as (id, root); None (and a finding) when malformed."""
        idt = self.advance()
        if idt[0] != "word":
            self.findings.append(message("c4.malformed-view"))
            return None
        nxt = self.advance()
        if nxt == ("word", "of"):
            scope = self.advance()
            if scope[0] != "word" or self.advance()[0] != "{":
                self.findings.append(message("c4.malformed-view"))
                return None
            return idt[1], scope[1]
        if nxt[0] != "{":
            self.findings.append(message("c4.malformed-view"))
            return None
        return idt[1], None


def _add_base(raw: _RawView, name: str) -> None:
    if name not in raw.base:
        raw.base.append(name)


def parse_views(root: Path, model: ModelParse) -> ViewsParse:
    """Parse `architecture/views.c4` (absent: an empty `views` block); the layout check guarantees its one block."""
    path = root / architecture()["views_file"]
    parser = _Parser(_tokenize(path.read_text(encoding="utf-8") if path.is_file() else EMPTY_VIEWS))
    model_roots = roots(model)
    scopes = {r: _scope(model, r) for r in model_roots}
    raw: list[_RawView] = []
    seen_ids: set[str] = set()
    parser.pos = 2  # past `views {`
    while parser.cur()[0] not in ("}", "eof"):
        if parser.advance() != ("word", "view"):
            parser.findings.append(message("c4.expected-view"))
            continue
        header = parser.header()
        if header is None:
            continue
        vid, scope_id = header
        if scope_id is None:
            parser.findings.append(message("c4.view-unscoped", view=vid))
        elif scope_id not in scopes:
            parser.findings.append(message("c4.view-scope-unknown", view=vid, root=scope_id))
        if scope_id in scopes:
            raw.append(parser.body(vid, scopes[scope_id], parser.findings))
        else:
            parser.body(vid, _scope(model, ""), [])
        if vid in seen_ids:
            parser.findings.append(message("c4.duplicate-view", view=vid))
        seen_ids.add(vid)
    depths = _view_depths(root=root, valid_ids=seen_ids, findings=parser.findings)
    views = [
        _build_view(spec=spec, depth=depths.get(spec.id, DEFAULT_VIEW_DEPTH), model=scopes[spec.root].model)
        for spec in raw
    ]
    return ViewsParse(views=views, findings=parser.findings)


def _view_depths(root: Path, valid_ids: set[str], findings: list[str]) -> dict[str, int]:
    """Per-view render depth from index.yaml `view_depth`; malformed entries are findings, not raises."""
    index = read_index(root)
    depth_map = index.get("view_depth") if isinstance(index, dict) else None
    if depth_map is None:
        return {}
    if not isinstance(depth_map, dict):
        findings.append(message("c4.view-depth-not-mapping"))
        return {}
    depths: dict[str, int] = {}
    for vid, value in depth_map.items():
        if vid not in valid_ids:
            findings.append(message("c4.view-depth-unknown-view", view=vid))
        elif not isinstance(value, int) or isinstance(value, bool) or value < 1:
            findings.append(message("c4.view-depth-invalid", view=vid, value=value))
        else:
            depths[vid] = value
    return depths


def _children_map(model: ModelParse) -> dict[str, list[str]]:
    kids: dict[str, list[str]] = {}
    for e in model.elements:
        if e.parent is not None:
            kids.setdefault(e.parent, []).append(e.id)
    return kids


def _ancestor_chain(eid: str) -> list[str]:
    """`eid` and every ancestor id, top-level first (`a.b.c` -> [a, a.b, a.b.c])."""
    parts = eid.split(".")
    return [".".join(parts[: i + 1]) for i in range(len(parts))]


def _subtree(root: str, kids: dict[str, list[str]]) -> list[str]:
    """Pre-order ids of `root` and all its descendants (model declaration order within a parent)."""
    out = [root]
    for child in kids.get(root, []):
        out.extend(_subtree(child, kids))
    return out


def _shown_ids(spec: _RawView, depth: int, model: ModelParse, kids: dict[str, list[str]]) -> set[str]:
    """Each base's subtree down to `depth`, plus every predicate-matched endpoint collapsed to `depth`
    and its ancestor chain."""
    shown: set[str] = set()
    for top in spec.base:
        for eid in _subtree(root=top, kids=kids):
            if _level(eid) <= depth:
                shown.add(eid)
    for r in model.relations:
        if _top(r.src) not in spec.src_anchors and _top(r.dst) not in spec.dst_anchors:
            continue
        for endpoint in (r.src, r.dst):
            shown.update(_ancestor_chain(_ancestor_at_level(eid=endpoint, level=min(depth, _level(endpoint)))))
    return shown


def _represent(eid: str, shown: set[str]) -> str | None:
    """The nearest shown ancestor of `eid` (itself if shown), or None."""
    for anc in reversed(_ancestor_chain(eid)):
        if anc in shown:
            return anc
    return None


def _view_edges(model: ModelParse, spec: _RawView, among: set[str], shown: set[str]) -> list[Edge]:
    """Relations projected onto shown representatives, deduped in first-seen order; an edge is legacy
    iff every contributing relation is."""
    contributors: dict[tuple[str, str], list[Relation]] = {}
    order: list[tuple[str, str]] = []
    for r in model.relations:
        in_view = (_top(r.src) in among and _top(r.dst) in among) or _top(r.src) in spec.src_anchors or _top(r.dst) in spec.dst_anchors
        if not in_view:
            continue
        rep_src, rep_dst = _represent(eid=r.src, shown=shown), _represent(eid=r.dst, shown=shown)
        if rep_src is None or rep_dst is None or rep_src == rep_dst:
            continue
        key = (rep_src, rep_dst)
        if key not in contributors:
            contributors[key] = []
            order.append(key)
        contributors[key].append(r)
    return [Edge(src=s, dst=d, legacy=all(r.legacy for r in contributors[(s, d)])) for s, d in order]


def _build_view(spec: _RawView, depth: int, model: ModelParse) -> View:
    """Expand base includes to `depth`; predicate pulls add only the matched endpoint and its ancestor
    chain. Deeper edges roll up to the cutoff."""
    kids = _children_map(model)
    shown = _shown_ids(spec=spec, depth=depth, model=model, kids=kids)
    edges = _view_edges(model=model, spec=spec, among=set(spec.base), shown=shown)
    node_ids = [e.id for e in model.elements if e.id in shown]
    return View(id=spec.id, title=spec.title, root=spec.root, node_ids=node_ids, edges=edges)
