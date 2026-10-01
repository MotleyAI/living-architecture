"""enforced-tags: every arc42 principle item carries a well-formed status tag."""

from __future__ import annotations

import re
from pathlib import Path

from living_architecture.contract import check_ids, message

_TAG_RE = re.compile(r"\[(enforced|review|target)\b([^\]]*)\]")
_TAG_START_RE = re.compile(r"\[(enforced|review|target)\b")
_FENCE_RE = re.compile(r"`{3,}|~{3,}")
_PRINCIPLE_ITEM_RE = re.compile(r"^( {0,3})(\d+)\.\s")


def _parse_tag_id(rest: str) -> str | None:
    """Tag id from ': <id>' — None when malformed (no colon, empty, or multi-line)."""
    if not rest.startswith(":"):
        return None
    tag_id = rest[1:].strip()
    if not tag_id or "\n" in tag_id:
        return None
    return tag_id


def _tag_occurrence(kind: str, rest: str, name: str, issue_key_re: re.Pattern[str]) -> tuple[bool, list[str]]:
    """(counts as status coverage, findings) for one bracket tag."""
    if kind == "review":
        return (True, []) if not rest else (False, [message("enforced-tags.malformed-review", doc=name)])
    tag_id = _parse_tag_id(rest)
    if tag_id is None:
        return False, [message("enforced-tags.malformed", kind=kind, doc=name)]
    if kind == "target":
        if issue_key_re.fullmatch(tag_id) is None:
            return False, [
                message("enforced-tags.target-mismatch", doc=name, tag_id=tag_id, pattern=issue_key_re.pattern)
            ]
        return True, []
    if tag_id.startswith("test:") and tag_id != "test:":
        return True, []
    if tag_id.startswith("arch_check:") and tag_id.removeprefix("arch_check:") in check_ids():
        return True, []
    return False, [message("enforced-tags.unknown-id", doc=name, tag_id=tag_id)]


def _strip_fences(text: str) -> str:
    """Blank out fenced code blocks so tags and numbered items inside are ignored."""
    out: list[str] = []
    fence = ""  # opening delimiter run; closer is delimiter-only, same char, >= length
    for line in text.splitlines():
        if not fence:
            m = _FENCE_RE.match(line.lstrip())
            if m:
                fence = m.group(0)
            out.append("" if m else line)
        else:
            m = _FENCE_RE.fullmatch(line.strip())
            if m and m.group(0)[0] == fence[0] and len(m.group(0)) >= len(fence):
                fence = ""
            out.append("")
    return "\n".join(out)


def _principle_items(text: str) -> list[tuple[str, str]]:
    """Top-level numbered items as (number, item text incl. continuation lines)."""
    items: list[tuple[str, str]] = []
    open_col = -1  # content column of the open item; -1 = closed
    for line in text.splitlines():
        m = _PRINCIPLE_ITEM_RE.match(line)
        # a number indented to the open item's content column is its content (CommonMark)
        if m and not (open_col >= 0 and len(m.group(1)) >= open_col):
            items.append((m.group(2), line))
            open_col = len(m.group(1)) + len(m.group(2)) + 2
        elif open_col >= 0 and line.strip() and not line.startswith("#"):
            num, body = items[-1]
            items[-1] = (num, body + "\n" + line)
        else:
            open_col = -1
    return items


def check_enforced_tags(root: Path, issue_key_re: re.Pattern[str]) -> list[str]:
    findings: list[str] = []
    for path in sorted((root / "architecture").glob("*.arc42.md")):
        text = _strip_fences(path.read_text(encoding="utf-8"))
        occurrences = list(_TAG_RE.finditer(text))
        for kind in ("enforced", "review", "target"):
            starts = sum(1 for m in _TAG_START_RE.finditer(text) if m.group(1) == kind)
            closed = sum(1 for m in occurrences if m.group(1) == kind)
            if starts != closed:
                findings.append(message("enforced-tags.malformed", kind=kind, doc=path.name))
        for m in occurrences:
            findings += _tag_occurrence(m.group(1), m.group(2), path.name, issue_key_re)[1]
        for num, body in _principle_items(text):
            covered = any(
                _tag_occurrence(t.group(1), t.group(2), path.name, issue_key_re)[0] for t in _TAG_RE.finditer(body)
            )
            if not covered:
                findings.append(message("enforced-tags.untagged-item", doc=path.name, number=num))
    return findings
