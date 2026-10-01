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


class Relation(BaseModel):
    src: str
    dst: str
    legacy: bool = False


class ModelParse(BaseModel):
    elements: list[Element]
    relations: list[Relation]
    findings: list[str]


_ELEMENT_RE = re.compile(r"^(\w+)\s*=\s*(\w+)\s+'([^']*)'(?:\s*\{)?\s*$")
_RELATION_RE = re.compile(r"^([\w.]+)\s*->\s*([\w.]+)(\s+#legacy)?\s*$")
_SPEC_ELEMENT_RE = re.compile(r"^element\s+(\w+)(?:\s*\{)?\s*$")
_TAG_DECL_RE = re.compile(r"^tag\s+\w+$")
_BLOCK_RE = re.compile(r"^(specification|model|views)\b")
_BRACES_ONLY_RE = re.compile(r"^[{}]+$")


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


def parse_model(root: Path) -> ModelParse:
    """Parse `architecture/model/*.c4` under the constrained authoring convention."""
    kinds: dict[str, bool] = {}
    elements: list[Element] = []
    seen_ids: set[str] = set()
    relations: list[Relation] = []
    rel_pairs: set[tuple[str, str]] = set()
    findings: list[str] = []
    for path in _model_files(root):
        _scan_model_file(
            path=path,
            kinds=kinds,
            elements=elements,
            seen_ids=seen_ids,
            relations=relations,
            rel_pairs=rel_pairs,
            findings=findings,
        )
    for element in elements:
        if element.kind not in kinds:
            findings.append(message("c4.undeclared-kind", element=element.id, kind=element.kind))
        element.virtual = kinds.get(element.kind, False)
    for relation in relations:
        for endpoint in (relation.src, relation.dst):
            if endpoint not in seen_ids:
                findings.append(
                    message("c4.unknown-endpoint", src=relation.src, dst=relation.dst, endpoint=endpoint)
                )
    return ModelParse(elements=elements, relations=relations, findings=findings)


def _scan_model_file(  # NOSONAR(S3776) — cohesive brace/region state machine; splitting scatters the model grammar
    path: Path,
    kinds: dict[str, bool],
    elements: list[Element],
    seen_ids: set[str],
    relations: list[Relation],
    rel_pairs: set[tuple[str, str]],
    findings: list[str],
) -> None:
    region: str | None = None
    depth = 0
    parents: list[str] = []
    spec_kind: str | None = None
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
        if region == "specification":
            for stmt in _split_spec_statements(code) if delta == 0 else [code]:
                spec_kind = _scan_spec_line(
                    code=stmt, kinds=kinds, spec_kind=spec_kind, delta=delta, findings=findings
                )
        elif region == "model":
            _scan_model_line(
                code=code,
                elements=elements,
                seen_ids=seen_ids,
                relations=relations,
                rel_pairs=rel_pairs,
                parents=parents,
                delta=delta,
                findings=findings,
            )
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


def _scan_model_line(
    code: str,
    elements: list[Element],
    seen_ids: set[str],
    relations: list[Relation],
    rel_pairs: set[tuple[str, str]],
    parents: list[str],
    delta: int,
    findings: list[str],
) -> None:
    m = _ELEMENT_RE.match(code)
    if m:
        kind, title = m.group(2), m.group(3)
        eid = f"{parents[-1]}.{m.group(1)}" if parents else m.group(1)
        if eid in seen_ids:
            findings.append(message("c4.duplicate-element", element=eid))
        else:
            seen_ids.add(eid)
            elements.append(Element(id=eid, kind=kind, title=title, parent=parents[-1] if parents else None))
        if delta > 0:
            parents.append(eid)
        return
    rel = _RELATION_RE.match(code)
    if rel:
        src, dst = rel.group(1), rel.group(2)
        legacy = rel.group(3) is not None
        if parents:
            findings.append(message("c4.relation-in-body", src=src, dst=dst, parent=parents[-1]))
        elif (src, dst) in rel_pairs:
            findings.append(message("c4.duplicate-relation", src=src, dst=dst))
        else:
            rel_pairs.add((src, dst))
            relations.append(Relation(src=src, dst=dst, legacy=legacy))
        return
    if _BRACES_ONLY_RE.match(code):
        return
    findings.append(message("c4.unrecognized-model-line", line=code))
