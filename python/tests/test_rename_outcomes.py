"""Every branch of every Python rename rule ends in an outcome: rewrite, blind spot, leftover or unrelated."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from living_architecture.contract import message
from living_architecture.refactor.member_scan import Blindspot, FormCall, plain_literal
from living_architecture.refactor.mentions import Mention
from living_architecture.refactor.outcomes import (
    blindspot_outcome,
    literal_outcomes,
    mention_outcome,
    string_member_outcome,
    target_outcome,
)
from living_architecture.refactor.python_source import SourceFile
from living_architecture.refactor.sites import Keeps, SiteError

OLD, NEW = "save_model", "store_model"


def _call(text: str) -> tuple[SourceFile, FormCall]:
    source = SourceFile(Path("/p/t.py"), text)
    assert source.tree is not None
    call = next(n for n in ast.walk(source.tree) if isinstance(n, ast.Call))
    literal = plain_literal(source, call.args[-1])
    assert literal is not None
    obj = call.args[0] if len(call.args) > 1 else None
    return source, FormCall(call=call, literal=literal[0], text=literal[1], obj=obj, forms=())


@pytest.mark.parametrize(
    ("renamed", "kind"),
    [([False], "unrelated"), ([], "unrelated"), ([True, True], "rewrite"), ([True, False], "blindspot")],
    ids=["other-class", "no-declaration", "renamed", "mixed"],
)
def test_string_member_outcome(renamed: list[bool], kind: str) -> None:
    source, call = _call('getattr(engine, "save_model")\n')
    outcome = string_member_outcome("t.py", source, call, renamed, OLD, NEW)
    assert (outcome.kind, outcome.span) == (kind, call.literal)
    assert [e.new_text for e in outcome.edits] == ([NEW] if kind == "rewrite" else [])
    if kind == "blindspot":
        assert outcome.finding is not None
        assert outcome.finding.text == message("refactor.mixed-target", path="t.py", line=1, receiver="engine", attr=OLD)


@pytest.mark.parametrize(
    ("project", "renamed", "member", "kind", "template"),
    [
        (True, None, True, "blindspot", "refactor.unresolved-target"),
        (True, None, False, "leftover", "refactor.leftover"),
        (False, None, True, "leftover", "refactor.leftover"),
        (True, [False, False, True], True, "rewrite", None),
        (True, [False, False, False], True, "unrelated", None),
    ],
    ids=["unresolved-member", "unresolved-other", "external", "renamed", "unchanged-declaration"],
)
def test_target_outcome(project: bool, renamed: list[bool] | None, member: bool, kind: str, template: str | None) -> None:
    source, call = _call('patch("pkg.Engine.save_model")\n')
    outcome = target_outcome("t.py", source, call, project_target=project, renamed=renamed, member=member, old=OLD, new=NEW)
    assert (outcome.kind, outcome.span) == (kind, call.literal)
    assert (outcome.finding.text.split(": ")[1] if outcome.finding else None) == (
        None if template is None else {"refactor.unresolved-target": "unresolved-target", "refactor.leftover": "leftover"}[template]
    )
    assert [source.text[e.start : e.end] for e in outcome.edits] == ([OLD] if kind == "rewrite" else [])


@pytest.mark.parametrize("literal", [None, (20, 30)], ids=["access", "string-form"])
def test_blindspot_outcome(literal: tuple[int, int] | None) -> None:
    source = SourceFile(Path("/p/t.py"), 'x = 1\ngetattr(o, "save_model")\n')
    spot = Blindspot(line=2, col=0, receiver="o", kind="Unknown", literal=literal)
    outcome = blindspot_outcome("t.py", source, spot, OLD)
    assert outcome.kind == "blindspot"
    assert outcome.span == (literal or (6, 6))


@pytest.mark.parametrize("rewrite", [True, False])
def test_mention_outcome(rewrite: bool) -> None:
    mention = Mention(start=4, end=14, line=1, where="comment", opens=False)
    outcome = mention_outcome("t.py", mention, rewrite=rewrite, old=OLD, new=NEW)
    assert (outcome.kind, outcome.span) == ("rewrite" if rewrite else "leftover", (4, 14))


def test_literal_outcomes_list_whole_value_literals_not_handled() -> None:
    text = (
        '"""save_model"""\n'
        'from operator import attrgetter\n'
        'a = attrgetter("save_model")\n'
        'b = "save_model is slow"\n'
        'c = f"save_model"\n'
        'd = getattr(o, "save_model")\n'
        "e = b'save_model'\n"
        "f = 'save_' 'model'\n"
    )
    source = SourceFile(Path("/p/t.py"), text)
    handled = text.index('"save_model")\n', text.index("getattr"))
    outcomes = literal_outcomes("t.py", source, OLD, lambda start, end: start <= handled < end)
    assert [(o.kind, source.line(o.span[0])) for o in outcomes] == [("leftover", 3), ("leftover", 8)]
    assert all(o.finding is not None and o.finding.text.endswith("string mentions save_model") for o in outcomes)


def _keeps(tmp_path: Path, *raws: str) -> Keeps:
    root = tmp_path.resolve()
    for rel in ("a.py", "b.py"):
        (root / rel).write_text("")
    return Keeps(raws, root, base=root)


def test_keeps_cover_lines_files_and_moves(tmp_path: Path) -> None:
    keeps = _keeps(tmp_path, "a.py:2", "b.py")
    assert [keeps.kept("a.py", 2), keeps.kept("a.py", 3), keeps.kept("b.py", None), keeps.kept("a.py", None)] == [
        True, False, True, False,
    ]
    keeps.check()


def test_keeps_report_the_first_unmatched_site(tmp_path: Path) -> None:
    keeps = _keeps(tmp_path, "a.py:2", "b.py")
    keeps.kept("b.py", 9)
    with pytest.raises(SiteError) as raised:
        keeps.check()
    assert (raised.value.template, raised.value.site) == ("refactor.keep-unmatched", "a.py:2")


def test_a_listing_check_marks_nothing(tmp_path: Path) -> None:
    keeps = _keeps(tmp_path, "a.py:2")
    assert keeps.kept("a.py", 2, mark=False)
    with pytest.raises(SiteError):
        keeps.check()
