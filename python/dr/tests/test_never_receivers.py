"""Receivers basedpyright types `Never`: blind spots of `dr-compliance --attr` and of a member rename."""

from __future__ import annotations

from pathlib import Path

import pytest
from project_files import file_tree, write_project
from refactor_cli import read, run

from living_architecture.cli.dr_compliance import dr_compliance
from living_architecture.contract import message
from living_architecture.lang import ExportRequest, FactQuery, LanguageServer

ATTR = "producer_root_model"
PLANNED = """\
from typing import Any, Optional

from pydantic import BaseModel


class Attach(BaseModel):
    producer_root_model: Optional[str] = None


def roots(planned, known: Any, loose) -> None:
    for a in list(getattr(planned, "attach_plans", ()) or ()):
        print(a.producer_root_model)
    g = getattr(planned, "attach_plans", ())
    print(list(g)[0].producer_root_model, [k.producer_root_model for k in list(g)])
    print(known.producer_root_model, loose.producer_root_model)
    print((g or planned).producer_root_model)


def typed(attach: Attach) -> Optional[str]:
    return attach.producer_root_model
"""
RECEIVERS = [(12, "a", "Never"), (14, "list(g)[0]", "Never"), (14, "k", "Never"), (15, "known", "Any"),
             (15, "loose", "Unknown"), (16, "(g or planned)", "Unknown")]


def _blindspots() -> list[str]:
    return [message("compliance.attr-blindspot", path="pkg/p.py", line=line, receiver=receiver, attr=ATTR, type=kind)
            for line, receiver, kind in RECEIVERS]


def test_compliance_reports_never_receivers_with_their_type(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = write_project(tmp_path / "p", {"pkg/p.py": PLANNED})
    monkeypatch.chdir(root)
    assert dr_compliance(["--select", "attr-blindspot", "--attr", ATTR, "pkg/p.py"]) == 1
    assert capsys.readouterr().out.splitlines() == _blindspots()


def test_a_member_rename_refuses_at_the_positions_compliance_reports(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = write_project(tmp_path / "p", {"pkg/p.py": PLANNED})
    before = file_tree(root)
    argv = ["--apply", "rename", "--file", "pkg/p.py", "--symbol", f"Attach.{ATTR}", "--new-name", "producer_population"]
    code, out, err = run(root, argv, monkeypatch, capsys)
    assert (code, out) == (1, "")
    assert err.splitlines() == [*_blindspots(), message("refactor.blindspots", count=6, names=f".{ATTR}")]
    assert file_tree(root) == before


def test_unsure_include_renames_never_receivers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = write_project(tmp_path / "p", {"pkg/p.py": PLANNED})
    argv = ["--apply", "rename", "--file", "pkg/p.py", "--symbol", f"Attach.{ATTR}", "--new-name", "producer_population",
            "--unsure", "include", "--allow-blindspots"]
    code, _out, err = run(root, argv, monkeypatch, capsys)
    assert (code, err.splitlines()) == (0, _blindspots())
    assert read(root, "pkg/p.py") == PLANNED.replace(ATTR, "producer_population")


def test_the_export_types_a_never_receiver(tmp_path: Path) -> None:
    root = write_project(tmp_path / "p", {"pkg/p.py": PLANNED}).resolve()
    path = root / "pkg" / "p.py"
    accesses = [PLANNED.index(f"{receiver}.{ATTR}") + len(receiver) + 1 for receiver in ("a", "known", "attach")]
    with LanguageServer(root) as server:
        server.open(path, PLANNED)
        index = server.export(ExportRequest(names=[ATTR], files=[path], facts=[
            FactQuery(path=path, offset=offset, kinds=("access",)) for offset in accesses]))
    assert [facts.access for facts in index.answers] == ["Never", "Any", None]
    members = [o.receiver for o in index.occurrences if o.kind == "member"]
    assert members == ["Never", "Never", "Never", "Any", "Unknown", "Unknown", None]


NAMED_NEVER = """\
from typing import NoReturn


class Never:
    id: int = 0


def read(x: Never) -> int:
    return x.id


def stop(y: NoReturn) -> None:
    print(y.id)
"""


def test_a_class_named_never_is_typed_and_noreturn_is_never(tmp_path: Path) -> None:
    root = write_project(tmp_path / "p", {"pkg/n.py": NAMED_NEVER}).resolve()
    path = root / "pkg" / "n.py"
    with LanguageServer(root) as server:
        server.open(path, NAMED_NEVER)
        index = server.export(ExportRequest(names=["id"], files=[path], facts=[
            FactQuery(path=path, offset=NAMED_NEVER.index(f"{name}.id") + 2, kinds=("access",)) for name in "xy"]))
    assert [facts.access for facts in index.answers] == [None, "Never"]
    assert [o.receiver for o in index.occurrences if o.kind == "member"] == [None, "Never"]
