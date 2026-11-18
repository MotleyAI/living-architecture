"""Python parameter renames: call keywords linked through the checker's signature, and unlinked keywords as blind spots."""

from __future__ import annotations

from pathlib import Path
from string import Template

import pytest
import yaml
from project_files import file_tree, write_project
from refactor_cli import read, run
from test_occurrence_index import EXPORT, Requests

from living_architecture.contract import message

OLD = "models"
NEW = "datasets"

DECORATED = Template("""\
import functools
from collections.abc import AsyncIterator, Callable, Iterator
from contextlib import asynccontextmanager, contextmanager
from typing import ParamSpec, TypeVar

P = ParamSpec("P")
R = TypeVar("R")


def logged(fn: Callable[P, R]) -> Callable[P, R]:
    @functools.wraps(fn)
    def inner(*args: P.args, **kwargs: P.kwargs) -> R:
        return fn(*args, **kwargs)

    return inner


@asynccontextmanager
async def engine(*, $engine: list[int]) -> AsyncIterator[list[int]]:
    yield $engine


@contextmanager
def sync_engine(*, $sync_engine: list[int]) -> Iterator[list[int]]:
    yield $sync_engine


@logged
def wrapped(*, $wrapped: list[int]) -> list[int]:
    return $wrapped


class C:
    @contextmanager
    def scope(self, *, $scope: list[int]) -> Iterator[list[int]]:
        yield $scope
""")
DECORATED_USE = Template("""\
from pkg.h import C, engine, sync_engine, wrapped


async def f(c: C) -> None:
    async with engine($engine=[1]) as e:
        print(e)
    with sync_engine($sync_engine=[1]) as s:
        print(s)
    with c.scope($scope=[1]) as t:
        print(t)
    print(wrapped($wrapped=[1]))
""")
SLOTS = {"engine": OLD, "sync_engine": OLD, "wrapped": OLD, "scope": OLD}


def _unlinked(path: str, line: int, callee: str, old: str = OLD) -> str:
    return message("refactor.unlinked-keyword", path=path, line=line, callee=callee, old=old)


def _closing(count: int, names: str = f"{OLD}=") -> str:
    return message("refactor.blindspots", count=count, names=names)


def _rename(symbol: str, *flags: str, rel: str = "pkg/h.py", new_name: str = NEW) -> list[str]:
    return ["--apply", "rename", "--file", rel, "--symbol", symbol, "--new-name", new_name, *flags]


@pytest.mark.parametrize(("symbol", "slot"), [("engine(models)", "engine"), ("sync_engine(models)", "sync_engine"),
                                              ("wrapped(models)", "wrapped"), ("C.scope(models)", "scope")])
def test_a_decorated_callee_keyword_follows_its_parameter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], symbol: str, slot: str
) -> None:
    root = write_project(tmp_path / "p", {"pkg/h.py": DECORATED.substitute(SLOTS),
                                          "pkg/use.py": DECORATED_USE.substitute(SLOTS)})
    code, _out, err = run(root, _rename(symbol), monkeypatch, capsys)
    assert (code, err) == (0, "")
    renamed = {**SLOTS, slot: NEW}
    assert read(root, "pkg/h.py") == DECORATED.substitute(renamed)
    assert read(root, "pkg/use.py") == DECORATED_USE.substitute(renamed)


PICKED = """\
from collections.abc import Iterator
from contextlib import contextmanager


@contextmanager
def one(*, models: int) -> Iterator[int]:
    yield models


@contextmanager
def two(*, models: int) -> Iterator[int]:
    yield models
"""
PICKED_USE = """\
import os

if os.environ.get("FAST"):
    from pkg.h import one as pick
else:
    from pkg.h import two as pick


def use() -> None:
    with pick(models=1):
        pass
"""


def test_a_keyword_linked_in_only_one_callable_alternative_is_unlinked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = write_project(tmp_path / "p", {"pkg/h.py": PICKED, "pkg/use.py": PICKED_USE})
    code, _out, err = run(root, _rename("one(models)", "--allow-blindspots"), monkeypatch, capsys)
    assert (code, err) == (0, _unlinked("pkg/use.py", 10, "pick") + "\n")
    assert read(root, "pkg/use.py") == PICKED_USE
    assert read(root, "pkg/h.py") == PICKED.replace("models", NEW, 2)


ERASED = Template("""\
import functools


def deco(fn): ...


@$decorator
def cached(models: int) -> int:
    return models


def plain(*, models: int) -> int:
    return models


def use() -> None:
    print(cached(models=1), plain(models=1))
""")


@pytest.mark.parametrize("decorator", ["functools.lru_cache", "deco"])
@pytest.mark.parametrize("apply", [True, False], ids=["apply", "dry-run"])
def test_a_keyword_of_an_erased_signature_refuses_the_rename(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], decorator: str, apply: bool
) -> None:
    root = write_project(tmp_path / "p", {"pkg/h.py": ERASED.substitute(decorator=decorator)})
    before = file_tree(root)
    code, out, err = run(root, _rename("cached(models)")[0 if apply else 1:], monkeypatch, capsys)
    assert (code, out) == (1, "")
    assert err.splitlines() == [_unlinked("pkg/h.py", 17, "cached"), _closing(1)]
    assert file_tree(root) == before


def test_allow_blindspots_lists_the_keyword_and_leaves_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    text = ERASED.substitute(decorator="functools.lru_cache")
    root = write_project(tmp_path / "p", {"pkg/h.py": text})
    code, _out, err = run(root, _rename("cached(models)", "--allow-blindspots"), monkeypatch, capsys)
    assert (code, err) == (0, _unlinked("pkg/h.py", 17, "cached") + "\n")
    assert read(root, "pkg/h.py") == text.replace("cached(models: int) -> int:\n    return models",
                                                  "cached(datasets: int) -> int:\n    return datasets")


def test_unsure_include_renames_the_unlinked_keyword(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    text = ERASED.substitute(decorator="functools.lru_cache")
    root = write_project(tmp_path / "p", {"pkg/h.py": text})
    flags = ("--unsure", "include", "--allow-blindspots")
    code, out, err = run(root, _rename("cached(models)", *flags), monkeypatch, capsys)
    assert (code, err) == (0, _unlinked("pkg/h.py", 17, "cached") + "\n")
    assert out.startswith(message("refactor.unsure-warning") + "\n")
    assert read(root, "pkg/h.py") == text.replace("cached(models", "cached(datasets").replace(
        "    return models\n\n\ndef plain", "    return datasets\n\n\ndef plain")


def test_a_kept_line_drops_its_unlinked_keyword(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    text = ERASED.substitute(decorator="functools.lru_cache")
    root = write_project(tmp_path / "p", {"pkg/h.py": text})
    code, _out, err = run(root, _rename("cached(models)", "--keep", "pkg/h.py:17"), monkeypatch, capsys)
    assert (code, err) == (0, "")
    assert "cached(models=1)" in read(root, "pkg/h.py")
    assert "def cached(datasets: int)" in read(root, "pkg/h.py")


MULTILINE = """\
import functools


class Box:
    @functools.lru_cache
    def cached(self, models: int) -> int:
        return models


def use(box: Box) -> None:
    box .  cached(models=1)
"""


def test_the_callee_text_collapses_whitespace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = write_project(tmp_path / "p", {"pkg/h.py": MULTILINE})
    code, _out, err = run(root, _rename("Box.cached(models)"), monkeypatch, capsys)
    assert code == 1
    assert err.splitlines() == [_unlinked("pkg/h.py", 11, "box . cached"), _closing(1)]


UNTYPED_CALLS = """\
class Model:
    def models(self) -> int:
        return 1


def models() -> int:
    return 1


def use(untyped, o) -> None:
    untyped(models=1)
    print(o.models)
"""


@pytest.mark.parametrize("symbol", ["Model", "models", "use"], ids=["class", "function", "other-function"])
def test_a_rename_of_no_parameter_or_field_lists_no_keyword(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], symbol: str
) -> None:
    root = write_project(tmp_path / "p", {"pkg/h.py": UNTYPED_CALLS})
    code, _out, err = run(root, _rename(symbol, new_name="renamed"), monkeypatch, capsys)
    assert (code, err) == (0, "")


def test_a_method_rename_lists_receivers_but_no_keyword(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = write_project(tmp_path / "p", {"pkg/h.py": UNTYPED_CALLS})
    code, _out, err = run(root, _rename("Model.models", new_name="renamed"), monkeypatch, capsys)
    blind = message("compliance.attr-blindspot", path="pkg/h.py", line=12, receiver="o", attr="models", type="Unknown")
    assert (code, err.splitlines()) == (1, [blind, _closing(1, ".models")])


PARAM_AND_UNTYPED = """\
from collections.abc import Callable
from typing import Any


def kwonly(*, models: int) -> int:
    return models


def use(untyped, o, a: Any, mixed: Callable[..., int] | Any, planned) -> None:
    kwonly(models=1)
    untyped(models=1)
    a(models=1)
    mixed(models=1)
    for never in list(getattr(planned, "fns", ()) or ()):
        never(models=1)
    print(o.models)
"""


def test_a_parameter_rename_lists_unknown_any_and_never_callees_but_no_receiver(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = write_project(tmp_path / "p", {"pkg/h.py": PARAM_AND_UNTYPED})
    code, _out, err = run(root, _rename("kwonly(models)"), monkeypatch, capsys)
    lines = [_unlinked("pkg/h.py", line, callee) for line, callee in [(11, "untyped"), (12, "a"), (13, "mixed"), (15, "never")]]
    assert (code, err.splitlines()) == (1, [*lines, _closing(4)])


MIXED_REPORT = """\
import functools


class Store:
    def get_model(self) -> int:
        return 1


@functools.lru_cache
def cached(models: int) -> int:
    return models


def use(o) -> None:
    print(o.get_model(), cached(models=1))
"""


def test_a_map_reports_members_and_keywords_in_one_closing_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    entries = [{"file": "pkg/h.py", "symbol": "Store.get_model", "new_name": "get_dataset"},
               {"file": "pkg/h.py", "symbol": "cached(models)", "new_name": NEW}]
    root = write_project(tmp_path / "p", {"pkg/h.py": MIXED_REPORT, "map.yaml": yaml.safe_dump(entries)})
    before = file_tree(root)
    code, out, err = run(root, ["rename-map", "map.yaml"], monkeypatch, capsys)
    assert (code, out) == (1, "")
    assert err.splitlines() == [
        message("compliance.attr-blindspot", path="pkg/h.py", line=15, receiver="o", attr="get_model", type="Unknown"),
        _unlinked("pkg/h.py", 15, "cached"),
        _closing(2, ".get_model, models="),
    ]
    assert file_tree(root) == before


RESOLVED = "def kwonly(*, models: int) -> int:\n    return models\n"


def _calls(callee: str, count: int) -> str:
    body = "".join(f"    print({callee}(models={i}))\n" for i in range(count))
    return f"from pkg.h import {callee}\n\n\ndef use() -> None:\n{body}"


def _exports(tmp_path: Path, name: str, files: dict[str, str], symbol: str, monkeypatch: pytest.MonkeyPatch,
             capsys: pytest.CaptureFixture[str]) -> int:
    """The export requests of one applied rename of `symbol`, which must rename every `models=` keyword."""
    root = write_project(tmp_path / name, files)
    requests = Requests()
    with monkeypatch.context() as patched:
        requests.install(patched)
        code, _out, err = run(root, _rename(symbol), patched, capsys)
    assert (code, err) == (0, "")
    assert "models=" not in read(root, "pkg/use.py")
    assert requests.per_occurrence() == {}
    return requests.sent[EXPORT]


def test_linking_sends_a_fixed_number_of_export_requests(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    decorated = DECORATED.substitute(SLOTS)
    resolved = [_exports(tmp_path, f"resolved{n}", {"pkg/h.py": RESOLVED, "pkg/use.py": _calls("kwonly", n)},
                         "kwonly(models)", monkeypatch, capsys) for n in (1, 10)]
    linked = [_exports(tmp_path, f"linked{n}", {"pkg/h.py": decorated, "pkg/use.py": _calls("wrapped", n)},
                       "wrapped(models)", monkeypatch, capsys) for n in (1, 10)]
    # The self-test and one export; the signature proof adds one probe round, whatever the number of keywords.
    assert resolved == [2, 2]
    assert linked == [3, 3]


def test_a_cached_rerun_links_the_same_keywords_without_an_export(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = write_project(tmp_path / "p", {"pkg/h.py": DECORATED.substitute(SLOTS),
                                          "pkg/use.py": DECORATED_USE.substitute(SLOTS)})
    argv = _rename("wrapped(models)")[1:]
    first = run(root, argv, monkeypatch, capsys)
    requests = Requests()
    with monkeypatch.context() as patched:
        requests.install(patched)
        second = run(root, argv, patched, capsys)
    assert first[0] == 0
    assert "+    print(wrapped(datasets=[1]))\n" in first[1]
    assert second == first
    assert requests.sent[EXPORT] == 0
