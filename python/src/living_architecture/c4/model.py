"""The constrained `.c4` model parser (element FQN = dotted path)."""

from __future__ import annotations

import re
from pathlib import Path

from pydantic import BaseModel

from living_architecture.contract import message


class Element(BaseModel):
    id: str
    kind: str
    title: str
    parent: str | None = None
    virtual: bool = False
    metadata: dict[str, str | list[str]] = {}
    metadata_problems: list[str] = []


class Relation(BaseModel):
    src: str
    dst: str
    legacy: bool = False


class ModelParse(BaseModel):
    elements: list[Element]
    relations: list[Relation]
    findings: list[str]
    metadata_findings: list[str] = []


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


def _c4_logical_lines(text: str) -> list[str]:
    """Comment-stripped lines with every unquoted `{`/`}` broken onto its own line."""
    decommented = "\n".join(strip_line_comment(line) for line in text.splitlines())
    out: list[str] = []
    in_q = False
    for ch in decommented:
        if ch == "'":
            in_q = not in_q
            out.append(ch)
        elif not in_q and ch == "{":
            out.append("{\n")
        elif not in_q and ch == "}":
            out.append("\n}\n")
        else:
            out.append(ch)
    return [line.strip() for line in "".join(out).splitlines() if line.strip()]


def _model_files(root: Path) -> list[Path]:
    return sorted((root / "architecture" / "model").glob("*.c4"))


class _Scan(BaseModel):
    """Accumulators shared by every model file of one parse."""

    kinds: dict[str, bool] = {}
    by_id: dict[str, Element] = {}
    duplicates: set[str] = set()
    with_metadata: set[str] = set()
    relations: list[Relation] = []
    rel_pairs: set[tuple[str, str]] = set()
    findings: list[str] = []
    metadata_findings: list[str] = []


class _MetadataBlock(BaseModel):
    """An open `metadata { }` block; `element` is None when its content is discarded."""

    element: str | None
    depth: int = 1
    lines: list[str] = []


def parse_model(root: Path) -> ModelParse:
    """Parse `architecture/model/*.c4` under the constrained authoring convention."""
    scan = _Scan()
    for path in _model_files(root):
        _scan_model_file(path=path, scan=scan)
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
        elements=elements, relations=scan.relations, findings=scan.findings, metadata_findings=scan.metadata_findings
    )


def _scan_model_file(path: Path, scan: _Scan) -> None:  # NOSONAR(S3776) — cohesive brace/region state machine
    region: str | None = None
    depth = 0
    parents: list[str] = []
    spec_kind: str | None = None
    meta: _MetadataBlock | None = None
    for code in _c4_logical_lines(path.read_text(encoding="utf-8")):
        if region is None:
            m = _BLOCK_RE.match(code)
            if m:
                region = m.group(1) if m.group(1) in ("specification", "model") else "other"
                depth = _brace_delta(code)
                if depth <= 0:
                    region = None
            continue
        delta = _brace_delta(code)
        if meta is not None:
            depth += delta
            meta.depth += delta
            if meta.depth > 0:
                meta.lines.append(code)
            else:
                _close_metadata(meta, scan)
                meta = None
            continue
        if region == "model" and parents and _METADATA_OPEN_RE.match(code):
            depth += delta
            meta = _open_metadata(element=parents[-1], code=code, scan=scan)
            continue
        if region == "specification":
            for stmt in _split_spec_statements(code) if delta == 0 else [code]:
                spec_kind = _scan_spec_line(
                    code=stmt, kinds=scan.kinds, spec_kind=spec_kind, delta=delta, findings=scan.findings
                )
        elif region == "model":
            _scan_model_line(code=code, scan=scan, parents=parents, delta=delta)
        if delta < 0:
            for _ in range(-delta):
                if parents:
                    parents.pop()
        depth += delta
        if depth <= 0:
            region = None
            parents.clear()
            spec_kind = None
        elif region == "specification" and depth == 1:
            spec_kind = None
    if meta is not None:
        _close_metadata(meta, scan)


def _open_metadata(element: str, code: str, scan: _Scan) -> _MetadataBlock:
    """Start a block for `element`; a duplicate element's block, or a second block, is discarded."""
    if element in scan.duplicates:
        return _MetadataBlock(element=None)
    if element in scan.with_metadata:
        _metadata_problem(scan, element, code)
        return _MetadataBlock(element=None)
    scan.with_metadata.add(element)
    return _MetadataBlock(element=element)


def _close_metadata(block: _MetadataBlock, scan: _Scan) -> None:
    if block.element is None:
        return
    values, problems = _parse_metadata(block.lines)
    scan.by_id[block.element].metadata = values
    for line in problems:
        _metadata_problem(scan, block.element, line)


def _metadata_problem(scan: _Scan, element: str, line: str) -> None:
    problem = message("c4.malformed-metadata", element=element, line=line)
    scan.by_id[element].metadata_problems.append(problem)
    scan.metadata_findings.append(problem)


def _parse_metadata(lines: list[str]) -> tuple[dict[str, str | list[str]], list[str]]:
    """`key 'v'` / `key ['a', 'b']` statements (arrays may span lines) and the text of each bad one."""
    values: dict[str, str | list[str]] = {}
    problems: list[str] = []
    pending = ""
    for line in lines:
        text = f"{pending} {line}" if pending else line
        pending = ""
        pos = 0
        while pos < len(text):
            m = _META_STMT_RE.match(text, pos)
            if m is None:
                rest = text[pos:].strip()
                if _META_OPEN_ARRAY_RE.fullmatch(rest):
                    pending = rest
                elif rest:
                    problems.append(rest)
                break
            if m.group(1) in values:
                problems.append(m.group(0).strip())
            else:
                raw = m.group(2)
                values[m.group(1)] = raw[1:-1] if raw.startswith("'") else [q[1:-1] for q in _QUOTED_RE.findall(raw)]
            pos = m.end()
    if pending:
        problems.append(pending)
    return values, problems


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
        src, dst = rel.group(1), rel.group(2)
        legacy = rel.group(3) is not None
        if parents:
            scan.findings.append(message("c4.relation-in-body", src=src, dst=dst, parent=parents[-1]))
        elif (src, dst) in scan.rel_pairs:
            scan.findings.append(message("c4.duplicate-relation", src=src, dst=dst))
        else:
            scan.rel_pairs.add((src, dst))
            scan.relations.append(Relation(src=src, dst=dst, legacy=legacy))
        return
    if _BRACES_ONLY_RE.match(code):
        return
    scan.findings.append(message("c4.unrecognized-model-line", line=code))
