"""Rule and conflict-check work that depends only on a file and a name runs once per run, not once per entry."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

import pytest
import yaml
from refactor_cli import read, run

from living_architecture.refactor import keyed, member_namespace
from living_architecture.refactor.python_source import SourceFile

MakeProject = Callable[..., Path]

KEYED_MODELS = """\
from pydantic import BaseModel


class A(BaseModel):
    columns: list[int] = []


class B(BaseModel):
    columns: list[int] = []
"""
KEYED_USE = """\
from pkg.models import A, B



def use() -> object:
    e = {"columns": []}
    g = {"columns": []}
    return (
        A(columns=[]),
        B(columns=[]),
        A.model_validate({"columns": []}),
        B.model_validate({"columns": []}),
        A.model_validate(e),
        B(**g),
    )
"""
KEYED_ENTRIES = [
    {"file": "pkg/models.py", "symbol": "A.columns", "new_name": "fields"},
    {"file": "pkg/models.py", "symbol": "B.columns", "new_name": "cols"},
]

MEMBER_MODELS = """\
class A:
    def save(self) -> int:
        return 1


class B:
    def save(self) -> int:
        return 2
"""
MEMBER_USE = """\
from pkg.models import A, B


def use(a: A, b: B) -> int:
    return a.save() + b.save()
"""
MEMBER_ENTRIES = [
    {"file": "pkg/models.py", "symbol": "A.save", "new_name": "store"},
    {"file": "pkg/models.py", "symbol": "B.save", "new_name": "store"},
]


def _project(typed_project: MakeProject, files: dict[str, str], entries: Sequence[Mapping[str, object]]) -> Path:
    return typed_project({**files, "map.yaml": yaml.safe_dump(list(entries), sort_keys=False)})


def test_entries_sharing_a_file_and_old_name_keep_their_own_keyed_edits(
    typed_project: MakeProject, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _project(typed_project, {"pkg/models.py": KEYED_MODELS, "pkg/use.py": KEYED_USE}, KEYED_ENTRIES)
    code, _, _ = run(root, ["--apply", "rename-map", "map.yaml"], monkeypatch, capsys)
    assert code == 0
    assert read(root, "pkg/use.py") == """\
from pkg.models import A, B



def use() -> object:
    e = {"fields": []}
    g = {"cols": []}
    return (
        A(fields=[]),
        B(cols=[]),
        A.model_validate({"fields": []}),
        B.model_validate({"cols": []}),
        A.model_validate(e),
        B(**g),
    )
"""


def test_keyed_sink_discovery_runs_once_per_file_and_old_name(
    typed_project: MakeProject, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _project(typed_project, {"pkg/models.py": KEYED_MODELS, "pkg/use.py": KEYED_USE}, KEYED_ENTRIES)
    calls: Counter[tuple[Path, str]] = Counter()
    discover = keyed._dict_names  # pyright: ignore[reportPrivateUsage]

    # `_dict_names` starts a file's keyed sink discovery for an old name.
    def spy(source: SourceFile, old: str) -> set[str]:
        calls[(source.path, old)] += 1
        return discover(source, old)

    monkeypatch.setattr(keyed, "_dict_names", spy)
    code, _, _ = run(root, ["rename-map", "map.yaml"], monkeypatch, capsys)
    assert code == 0
    assert calls == Counter({(root / "pkg" / "use.py", "columns"): 1})


def test_member_check_scans_the_project_once_per_new_name(
    typed_project: MakeProject, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _project(typed_project, {"pkg/models.py": MEMBER_MODELS, "pkg/use.py": MEMBER_USE}, MEMBER_ENTRIES)
    calls: Counter[tuple[str, str]] = Counter()
    gate = member_namespace.may_name

    # `may_name` gates each project file of the scan for the classes declaring a member name.
    def spy(pattern: re.Pattern[str], text: str) -> bool:
        calls[(pattern.pattern, text)] += 1
        return gate(pattern, text)

    monkeypatch.setattr(member_namespace, "may_name", spy)
    code, out, err = run(root, ["rename-map", "map.yaml"], monkeypatch, capsys)
    assert (code, err) == (0, "")
    assert "a.store() + b.store()" in out
    assert calls, "the member namespace check never scanned the project"
    assert {k: n for k, n in calls.items() if n > 1} == {}
