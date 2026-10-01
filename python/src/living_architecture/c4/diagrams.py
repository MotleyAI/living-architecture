"""Mermaid blocks in arc42 docs: regeneration (`la-arch-diagrams`) and the diagrams-fresh check."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

from living_architecture.c4.index import read_index
from living_architecture.c4.mermaid import render_mermaid
from living_architecture.c4.model import ModelParse, parse_model
from living_architecture.c4.views import View, ViewsParse, parse_views
from living_architecture.contract import message

_MARKER_RE = re.compile(r"<!--\s+(/?)likec4:(\w+)\s+-->")


class DiagramsError(ValueError):
    """The mapped docs cannot be regenerated."""


def _read_exact(path: Path) -> str:
    """Read preserving exact bytes (no universal-newline translation) for byte-for-byte checks."""
    return path.read_bytes().decode("utf-8")


def _is_arc42_doc_key(doc_key: object) -> bool:
    """True only for a direct architecture/<name>.arc42.md child (rejects traversal/nesting)."""
    if not (isinstance(doc_key, str) and doc_key.endswith(".arc42.md")):
        return False
    parts = Path(doc_key).parts
    return len(parts) == 2 and parts[0] == "architecture"


def _canonical_block(view: View, model: ModelParse) -> str:
    return f"<!-- likec4:{view.id} -->\n{render_mermaid(view, model)}\n<!-- /likec4:{view.id} -->"


def _marker_span(text: str, vid: str) -> tuple[tuple[int, int] | None, str | None]:
    """(span, error): the open→close span, or None + one of missing/duplicate/order.

    Every whitespace form is counted via _MARKER_RE, so a stray variant marker for the
    same view (e.g. an extra double-space `<!--  likec4:x -->`) cannot slip past as fresh.
    """
    matches = [m for m in _MARKER_RE.finditer(text) if m.group(2) == vid]
    opens = [m for m in matches if not m.group(1)]
    closes = [m for m in matches if m.group(1)]
    if not opens or not closes:
        return None, "missing"
    if len(opens) > 1 or len(closes) > 1:
        return None, "duplicate"
    if closes[0].start() < opens[0].start():
        return None, "order"
    return (opens[0].start(), closes[0].end()), None


def _diagrams_map(root: Path) -> object:
    """The index.yaml `diagrams` value, or a message explaining why it is unusable (never raises)."""
    index = read_index(root)
    if isinstance(index, str):
        return index
    diagrams = index.get("diagrams")
    return message("c4.no-diagrams-block") if diagrams is None else diagrams


def _bad_diagrams_reason(diagrams: object) -> str:
    return diagrams if isinstance(diagrams, str) else message("c4.diagrams-not-mapping")


def _rewrite_markers(text: str, vids: Any, by_id: dict[str, View], model: ModelParse, doc_key: str) -> str:
    """Rewrite every mapped view's marker block in one doc's text; raise on missing view/marker."""
    for vid in vids:
        view = by_id.get(vid)
        if view is None:
            raise DiagramsError(message("arch-diagrams.view-undefined", view=vid, doc=doc_key))
        span, error = _marker_span(text=text, vid=vid)
        if error is not None or span is None:
            raise DiagramsError(message("arch-diagrams.marker", doc=doc_key, problem=error, view=vid))
        start, end = span
        text = text[:start] + _canonical_block(view, model) + text[end:]
    return text


def generate(root: Path) -> list[str]:
    """Rewrite each mapped doc's marker blocks from the model; return changed repo-relative paths."""
    diagrams = _diagrams_map(root)
    if not isinstance(diagrams, dict):
        raise DiagramsError(_bad_diagrams_reason(diagrams))
    model = parse_model(root)
    views = parse_views(root=root, model=model)
    problems = model.findings + views.findings
    if problems:
        raise DiagramsError(message("arch-diagrams.parse-findings", findings="\n".join(problems)))
    by_id = {v.id: v for v in views.views}
    changed: list[str] = []
    for doc_key, vids in diagrams.items():
        if not _is_arc42_doc_key(doc_key):
            raise DiagramsError(message("arch-diagrams.bad-key", key=doc_key))
        doc_path = root / doc_key
        text = _read_exact(doc_path)
        new_text = _rewrite_markers(text=text, vids=vids, by_id=by_id, model=model, doc_key=doc_key)
        if new_text != text:
            doc_path.write_text(new_text, encoding="utf-8", newline="")
            changed.append(doc_key)
    return changed


def run(root: Path) -> int:
    """`la-arch-diagrams`: print each rewritten doc."""
    try:
        changed = generate(root)
    except (ValueError, OSError) as exc:
        print(message("arch-diagrams.error", error=str(exc)), file=sys.stderr)
        return 1
    for doc_key in changed:
        print(doc_key)
    return 0


def _validate_entry(doc_key: object, vids: object) -> tuple[list[str], list[str] | None]:
    if not _is_arc42_doc_key(doc_key):
        return [message("diagrams-fresh.bad-key", key=doc_key)], None
    if not isinstance(vids, list):
        return [message("diagrams-fresh.not-a-list", key=doc_key)], None
    if not vids:
        return [message("diagrams-fresh.empty", key=doc_key)], None
    findings: list[str] = []
    seen: set[str] = set()
    valid: list[str] = []
    ok = True
    for vid in vids:
        if not isinstance(vid, str) or not vid:
            findings.append(message("diagrams-fresh.invalid-view-id", key=doc_key, view=vid))
            ok = False
        elif vid in seen:
            findings.append(message("diagrams-fresh.duplicate-view-id", key=doc_key, view=vid))
            ok = False
        else:
            seen.add(vid)
            valid.append(vid)
    return findings, (valid if ok else None)


def _collect_mapping(diagrams: object, findings: list[str]) -> dict[str, list[str]]:
    """Validated doc -> view-ids mapping; appends schema findings, fail-closed on bad input."""
    if not isinstance(diagrams, dict):
        findings.append(message("diagrams-fresh.unusable", reason=_bad_diagrams_reason(diagrams)))
        return {}
    mapping: dict[str, list[str]] = {}
    for doc_key, vids in diagrams.items():
        entry_findings, valid = _validate_entry(doc_key=doc_key, vids=vids)
        findings += entry_findings
        if valid is not None:
            mapping[doc_key] = valid
    return mapping


def check_diagrams_fresh(root: Path, model: ModelParse, views: ViewsParse) -> list[str]:
    """Fail-closed freshness check surfaced by the arch-check; never raises on malformed input."""
    findings = [message("diagrams-fresh.parse", finding=f) for f in model.findings + views.findings]
    mapping = _collect_mapping(diagrams=_diagrams_map(root), findings=findings)
    findings += _check_freshness(root=root, model=model, views=views, mapping=mapping)
    findings += _check_orphan_markers(root=root, mapping=mapping)
    return findings


def _check_freshness(root: Path, model: ModelParse, views: ViewsParse, mapping: dict[str, list[str]]) -> list[str]:
    by_id = {v.id: v for v in views.views}
    findings: list[str] = []
    for doc_key, vids in mapping.items():
        doc_path = root / doc_key
        if not doc_path.exists():
            findings.append(message("diagrams-fresh.doc-missing", doc=doc_key))
            continue
        text = _read_exact(doc_path)
        for vid in vids:
            view = by_id.get(vid)
            if view is None:
                findings.append(message("diagrams-fresh.view-unknown", view=vid, doc=doc_key))
                continue
            span, error = _marker_span(text=text, vid=vid)
            if error is not None:
                findings.append(message(f"diagrams-fresh.marker-{error}", doc=doc_key, view=vid))
            elif span is not None and text[span[0] : span[1]] != _canonical_block(view, model):
                findings.append(message("diagrams-fresh.stale", doc=doc_key, view=vid))
    return findings


def _check_orphan_markers(root: Path, mapping: dict[str, list[str]]) -> list[str]:
    findings: list[str] = []
    for doc_path in sorted((root / "architecture").glob("*.arc42.md")):
        doc_key = f"architecture/{doc_path.name}"
        mapped = set(mapping.get(doc_key, []))
        for m in _MARKER_RE.finditer(_read_exact(doc_path)):
            vid = m.group(2)
            if vid in mapped:
                continue
            kind = "closing" if m.group(1) == "/" else "opening"
            findings.append(message("diagrams-fresh.orphan-marker", doc=doc_key, kind=kind, view=vid))
    return findings
