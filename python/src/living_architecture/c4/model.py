"""The constrained `.c4` model parser (element FQN = dotted path; relations resolve inside their root)."""

from __future__ import annotations

import re
from pathlib import Path

from pydantic import BaseModel

from living_architecture.contract import architecture, message


class Element(BaseModel):
    id: str
    kind: str
    title: str
    parent: str | None = None
    virtual: bool = False
    has_metadata: bool = False
    metadata: dict[str, str | list[str]] = {}
    metadata_problems: list[str] = []


class Relation(BaseModel):
    src: str
    dst: str
    legacy: bool = False


Pos = tuple[int, int]
"""A 0-based (line, column) position: the `splitlines` line index and the offset within that line."""


class MetadataSpan(BaseModel):
    """(start, end) positions, end exclusive, of an element's metadata block and of each key's statement."""

    block: tuple[Pos, Pos]
    keys: dict[str, tuple[Pos, Pos]]


class ModelParse(BaseModel):
    elements: list[Element]
    relations: list[Relation]
    findings: list[str]
    metadata_findings: list[str] = []
    spans: dict[str, MetadataSpan] = {}


_ELEMENT_RE = re.compile(r"^(\w+)\s*=\s*(\w+)\s+'([^']*)'(?:\s*\{)?\s*$")
_RELATION_RE = re.compile(r"^([\w.]+)\s*->\s*([\w.]+)(\s+#legacy)?\s*$")
_SPEC_ELEMENT_RE = re.compile(r"^element\s+(\w+)(?:\s*\{)?\s*$")
_TAG_DECL_RE = re.compile(r"^tag\s+\w+$")
_BLOCK_RE = re.compile(r"^(specification|model|views)\b")
_BRACES_ONLY_RE = re.compile(r"^[{}]+$")
_METADATA_OPEN_RE = re.compile(r"^metadata\s*\{$")
_QUOTED = r"'[^']*'"
_META_STMT_RE = re.compile(rf"\s*(\w+)\s+({_QUOTED}|\[\s*(?:{_QUOTED}(?:\s*,\s*{_QUOTED})*)?\s*\])")
_META_OPEN_ARRAY_RE = re.compile(rf"\s*\w+\s+\[\s*(?:{_QUOTED}(?:\s*,\s*{_QUOTED})*\s*,?)?\s*$")
_QUOTED_RE = re.compile(_QUOTED)


def is_or_ancestor(anc: str, eid: str) -> bool:
    return anc == eid or eid.startswith(anc + ".")


def strip_line_comment(line: str) -> str:
    """Drop a trailing `//` comment, leaving single-quoted spans untouched."""
    out: list[str] = []
    in_q = False
    i = 0
    while i < len(line):
        ch = line[i]
        if ch == "'":
            in_q = not in_q
            out.append(ch)
        elif not in_q and line[i : i + 2] == "//":
            break
        else:
            out.append(ch)
        i += 1
    return "".join(out)


def _brace_delta(code: str) -> int:
    depth = 0
    in_q = False
    for ch in code:
        if ch == "'":
            in_q = not in_q
        elif not in_q and ch == "{":
            depth += 1
        elif not in_q and ch == "}":
            depth -= 1
    return depth


def _c4_logical_lines(text: str) -> list[tuple[int, int, str]]:
    """Comment-stripped (line index, column, code) pieces with every unquoted `{`/`}` broken onto its own piece."""
    out: list[tuple[int, int, str]] = []
    in_q = False
    for index, line in enumerate(strip_line_comment(raw) for raw in text.splitlines()):
        start = 0
        for i, ch in enumerate(line):
            if ch == "'":
                in_q = not in_q
            elif not in_q and ch == "{":
                _add_piece(out, index, line[start : i + 1], start)
                start = i + 1
            elif not in_q and ch == "}":
                _add_piece(out, index, line[start:i], start)
                _add_piece(out, index, ch, i)
                start = i + 1
        _add_piece(out, index, line[start:], start)
    return out


def _add_piece(out: list[tuple[int, int, str]], index: int, piece: str, start: int) -> None:
    if code := piece.strip():
        out.append((index, start + len(piece) - len(piece.lstrip()), code))


class _Scan(BaseModel):
    """Accumulators shared by every model file of one parse."""

    kinds: dict[str, bool] = {}
    by_id: dict[str, Element] = {}
    duplicates: set[str] = set()
    relations: list[Relation] = []
    rel_pairs: set[tuple[str, str]] = set()
    findings: list[str] = []
    metadata_findings: list[str] = []
    spans: dict[str, MetadataSpan] = {}


class _MetadataBlock(BaseModel):
    """An open `metadata { }` block; `element` is None when its content is discarded."""

    element: str | None
    start: Pos
    depth: int = 1
    lines: list[tuple[int, int, str]] = []


class _TextState(BaseModel):
    """Where the scan of one model text stands: open region, brace depth, enclosing elements, open metadata block."""

    region: str | None = None
    depth: int = 0
    parents: list[str] = []
    spec_kind: str | None = None
    meta: _MetadataBlock | None = None


class _Statements(BaseModel):
    """A metadata block's statements: the values, the text of each bad one, and each key's span."""

    values: dict[str, str | list[str]] = {}
    problems: list[str] = []
    keys: dict[str, tuple[Pos, Pos]] = {}


class _MetadataText(BaseModel):
    """One metadata line at `at`, prefixed (up to `base`) by an unfinished array statement that starts at `carried`."""

    text: str
    base: int
    at: Pos
    carried: Pos

    def pos(self, offset: int) -> Pos:
        """Where `offset` in `text` sits; any offset in the carried prefix maps to the carried statement's start."""
        return self.carried if offset < self.base else (self.at[0], self.at[1] + offset - self.base)


def parse_model(root: Path) -> ModelParse:
    """Parse `architecture/model.c4` under the constrained authoring convention."""
    return parse_model_files([root / architecture()["model_file"]])


def parse_model_files(paths: list[Path]) -> ModelParse:
    """Parse `paths` in order as one model."""
    return parse_model_texts([path.read_text(encoding="utf-8") for path in paths])


def parse_model_texts(texts: list[str]) -> ModelParse:
    """Parse `texts` in order as one model; `spans` index the lines of the text each element is declared in."""
    scan = _Scan()
    for text in texts:
        _scan_model_text(text=text, scan=scan)
    elements = list(scan.by_id.values())
    for element in elements:
        if element.kind not in scan.kinds:
            scan.findings.append(message("c4.undeclared-kind", element=element.id, kind=element.kind))
        element.virtual = scan.kinds.get(element.kind, False)
    for relation in scan.relations:
        for endpoint in (relation.src, relation.dst):
            if endpoint not in scan.by_id:
                scan.findings.append(
                    message("c4.unknown-endpoint", src=relation.src, dst=relation.dst, endpoint=endpoint)
                )
    return ModelParse(
        elements=elements,
        relations=scan.relations,
        findings=scan.findings,
        metadata_findings=scan.metadata_findings,
        spans=scan.spans,
    )


def _scan_model_text(text: str, scan: _Scan) -> None:
    state = _TextState()
    end: Pos = (0, 0)
    for lineno, col, code in _c4_logical_lines(text):
        end = (lineno, col + len(code))
        if state.region is None:
            _enter_region(state, code)
        elif state.meta is not None:
            _metadata_line(state, state.meta, scan, (lineno, col), code)
        elif state.region == "model" and state.parents and _METADATA_OPEN_RE.match(code):
            state.depth += _brace_delta(code)
            state.meta = _open_metadata(element=state.parents[-1], code=code, scan=scan, start=(lineno, col))
        else:
            _region_line(state, scan, code)
    if state.meta is not None:
        _close_metadata(state.meta, scan, end=end)


def _enter_region(state: _TextState, code: str) -> None:
    m = _BLOCK_RE.match(code)
    if m:
        state.region = m.group(1) if m.group(1) in ("specification", "model") else "other"
        state.depth = _brace_delta(code)
        if state.depth <= 0:
            state.region = None


def _metadata_line(state: _TextState, meta: _MetadataBlock, scan: _Scan, at: Pos, code: str) -> None:
    delta = _brace_delta(code)
    state.depth += delta
    meta.depth += delta
    if meta.depth > 0:
        meta.lines.append((*at, code))
    else:
        _close_metadata(meta, scan, end=(at[0], at[1] + len(code)))
        state.meta = None


def _region_line(state: _TextState, scan: _Scan, code: str) -> None:
    delta = _brace_delta(code)
    if state.region == "specification":
        for stmt in _split_spec_statements(code) if delta == 0 else [code]:
            state.spec_kind = _scan_spec_line(
                code=stmt, kinds=scan.kinds, spec_kind=state.spec_kind, delta=delta, findings=scan.findings
            )
    elif state.region == "model":
        _scan_model_line(code=code, scan=scan, parents=state.parents, delta=delta)
    if delta < 0:
        del state.parents[max(0, len(state.parents) + delta) :]
    state.depth += delta
    if state.depth <= 0:
        state.region = None
        state.parents.clear()
        state.spec_kind = None
    elif state.region == "specification" and state.depth == 1:
        state.spec_kind = None


def _open_metadata(element: str, code: str, scan: _Scan, start: Pos) -> _MetadataBlock:
    """Start a block for `element`; a duplicate element's block, or a second block, is discarded."""
    if element in scan.duplicates:
        return _MetadataBlock(element=None, start=start)
    if scan.by_id[element].has_metadata:
        _metadata_problem(scan, element, code)
        return _MetadataBlock(element=None, start=start)
    scan.by_id[element].has_metadata = True
    return _MetadataBlock(element=element, start=start)


def _close_metadata(block: _MetadataBlock, scan: _Scan, end: Pos) -> None:
    if block.element is None:
        return
    parsed = _parse_metadata(block.lines)
    scan.by_id[block.element].metadata = parsed.values
    scan.spans[block.element] = MetadataSpan(block=(block.start, end), keys=parsed.keys)
    for line in parsed.problems:
        _metadata_problem(scan, block.element, line)


def _metadata_problem(scan: _Scan, element: str, line: str) -> None:
    problem = message("c4.malformed-metadata", element=element, line=line)
    scan.by_id[element].metadata_problems.append(problem)
    scan.metadata_findings.append(problem)


def _parse_metadata(lines: list[tuple[int, int, str]]) -> _Statements:
    """`key 'v'` / `key ['a', 'b']` statements (arrays may span lines) of (line, column, code) pieces."""
    out = _Statements()
    carried, carried_at = "", (0, 0)
    for lineno, col, line in lines:
        piece = _MetadataText(
            text=f"{carried} {line}" if carried else line,
            base=len(carried) + 1 if carried else 0,
            at=(lineno, col),
            carried=carried_at,
        )
        carried, carried_at = _parse_statements(piece, out)
    if carried:
        out.problems.append(carried)
    return out


def _parse_statements(piece: _MetadataText, out: _Statements) -> tuple[str, Pos]:
    """Record `piece`'s statements in `out`; the unfinished array statement it ends with ("" if none) and its start."""
    text, pos = piece.text, 0
    while pos < len(text):
        m = _META_STMT_RE.match(text, pos)
        if m is None:
            tail = text[pos:]
            rest = tail.strip()
            if _META_OPEN_ARRAY_RE.fullmatch(rest):
                return rest, piece.pos(pos + len(tail) - len(tail.lstrip()))
            if rest:
                out.problems.append(rest)
            break
        _record_statement(m, piece, out)
        pos = m.end()
    return "", (0, 0)


def _record_statement(m: re.Match[str], piece: _MetadataText, out: _Statements) -> None:
    key, raw = m.group(1), m.group(2)
    if key in out.values:
        out.problems.append(m.group(0).strip())
        return
    out.values[key] = raw[1:-1] if raw.startswith("'") else [q[1:-1] for q in _QUOTED_RE.findall(raw)]
    out.keys[key] = (piece.pos(m.start(1)), piece.pos(m.end(2)))


def _split_spec_statements(code: str) -> list[str]:
    """Split a brace-free specification line into its `element`/`tag` statements."""
    return [part for part in re.split(r"\s+(?=(?:element|tag)\b)", code) if part]


def _scan_spec_line(
    code: str, kinds: dict[str, bool], spec_kind: str | None, delta: int, findings: list[str]
) -> str | None:
    m = _SPEC_ELEMENT_RE.match(code)
    if m:
        kinds.setdefault(m.group(1), False)
        return m.group(1) if delta > 0 else spec_kind
    if _TAG_DECL_RE.match(code) or _BRACES_ONLY_RE.match(code):
        return spec_kind
    if code.startswith("#") and spec_kind is not None and code == "#virtual":
        kinds[spec_kind] = True
        return spec_kind
    findings.append(message("c4.unrecognized-spec-line", line=code))
    return spec_kind


def _scan_model_line(code: str, scan: _Scan, parents: list[str], delta: int) -> None:
    m = _ELEMENT_RE.match(code)
    if m:
        kind, title = m.group(2), m.group(3)
        eid = f"{parents[-1]}.{m.group(1)}" if parents else m.group(1)
        if eid in scan.by_id:
            scan.findings.append(message("c4.duplicate-element", element=eid))
            scan.duplicates.add(eid)
        else:
            scan.by_id[eid] = Element(id=eid, kind=kind, title=title, parent=parents[-1] if parents else None)
        if delta > 0:
            parents.append(eid)
        return
    rel = _RELATION_RE.match(code)
    if rel:
        _scan_relation(rel, scan, parents)
    elif not _BRACES_ONLY_RE.match(code):
        scan.findings.append(message("c4.unrecognized-model-line", line=code))


def _scan_relation(rel: re.Match[str], scan: _Scan, parents: list[str]) -> None:
    src, dst = rel.group(1), rel.group(2)
    legacy = rel.group(3) is not None
    if not parents:
        scan.findings.append(message("c4.relation-outside-root", src=src, dst=dst))
        return
    if len(parents) > 1:
        scan.findings.append(message("c4.relation-in-body", src=src, dst=dst, parent=parents[-1]))
        return
    src, dst = f"{parents[0]}.{src}", f"{parents[0]}.{dst}"
    if (src, dst) in scan.rel_pairs:
        scan.findings.append(message("c4.duplicate-relation", src=src, dst=dst))
    else:
        scan.rel_pairs.add((src, dst))
        scan.relations.append(Relation(src=src, dst=dst, legacy=legacy))


def project(model: ModelParse, root: str) -> ModelParse:
    """The elements and relations under `root`, with the root prefix stripped (the root itself dropped)."""
    prefix = root + "."

    def local(eid: str) -> str:
        return eid[len(prefix) :]

    elements = [
        e.model_copy(update={"id": local(e.id), "parent": None if e.parent == root else local(e.parent or "")})
        for e in model.elements
        if e.id.startswith(prefix)
    ]
    relations = [
        Relation(src=local(r.src), dst=local(r.dst), legacy=r.legacy)
        for r in model.relations
        if r.src.startswith(prefix) and r.dst.startswith(prefix)
    ]
    return ModelParse(elements=elements, relations=relations, findings=[])


def roots(model: ModelParse) -> list[str]:
    """Top-level element ids, in model order."""
    return [e.id for e in model.elements if e.parent is None]
