"""The occurrence index's parts on their own: the class graph's roots, the per-run text tables, the positions a run
asks about, and the cache fingerprint's interpreter fallback."""

from __future__ import annotations

import ast
import json
import os
import re
import stat
import sys
from pathlib import Path

import pytest

from trmv.lang import Span
from trmv.refactor.compound import is_compound
from trmv.refactor.hierarchy import ClassGraph
from trmv.refactor.index_cache import (  # pyright: ignore[reportPrivateUsage]
    _config_chain,
    _jsonc,
    fingerprint,
)
from trmv.refactor.occurrence_index import candidate_files, fact_queries
from trmv.refactor.python_source import SourceFile
from trmv.refactor.text_tables import TextTables, declared_name

_WORD = re.compile(r"\w+")

# ---- the class graph


class _ByName:
    """Definitions resolving a base name to the class of that name in the same file, as the checker would."""

    def __init__(self, source: SourceFile) -> None:
        assert source.tree is not None
        self.source = source
        self.classes = {n.name: n for n in ast.walk(source.tree) if isinstance(n, ast.ClassDef)}

    def definition(self, path: Path, offset: int) -> list[Span]:
        found = self.classes.get(_WORD.match(self.source.text, offset).group())  # pyright: ignore[reportOptionalMemberAccess]
        span = self.source.name_span(found) if found is not None else None
        return [Span(path=path, start=span[0], end=span[1])] if span is not None else []


GRAPH = """from missing import Unknown


class A:
    def run(self) -> int: ...


class B(A):
    def run(self) -> int: ...


class C(A):
    pass


class D(B, C):
    def run(self) -> int: ...


class M:
    def run(self) -> int: ...


class E(M, A):
    pass


class F(Unknown):
    def run(self) -> int: ...
"""


def _graph() -> tuple[ClassGraph, SourceFile, dict[str, ast.ClassDef]]:
    source = SourceFile(Path("/p/m.py"), GRAPH)
    definitions = _ByName(source)
    return ClassGraph(definitions, lambda path: source if path == source.path else None), source, definitions.classes


def _roots(name: str) -> set[str]:
    graph, source, classes = _graph()
    by_key = {graph.of(source, node).key: n for n, node in classes.items()}
    return {by_key[k] for k in graph.roots(graph.of(source, classes[name]), "run")}


@pytest.mark.parametrize(
    ("cls", "roots"),
    [("A", {"A"}), ("B", {"A"}), ("C", {"A"}), ("D", {"A"}), ("M", {"M"}), ("E", {"M", "A"}), ("F", {"F"})],
    ids=["root", "override", "inherited", "diamond", "mixin", "both-bases", "unresolved-base"],
)
def test_roots_climb_every_base_that_has_the_member(cls: str, roots: set[str]) -> None:
    assert _roots(cls) == roots


def test_a_cycle_in_the_bases_ends() -> None:
    source = SourceFile(Path("/p/c.py"), "class X(Y):\n    def run(self) -> int: ...\n\n\nclass Y(X):\n    pass\n")
    definitions = _ByName(source)
    graph = ClassGraph(definitions, lambda path: source)
    x = graph.of(source, definitions.classes["X"])
    assert graph.roots(x, "run") <= {x.key, graph.of(source, definitions.classes["Y"]).key}


# ---- the per-run text tables

DECLARED = """class SaveModel:
    save_models = 1

    def save_model_now(self, save_model_arg: int) -> None:
        self.saveModel = save_model_arg


def model_save() -> None:
    savemodel = 'save_model'
    x = "save_model"
"""


def test_compounds_are_exactly_the_declarations_is_compound_finds(tmp_path: Path) -> None:
    (tmp_path / "m.py").write_text(DECLARED, encoding="utf-8")
    source = SourceFile(tmp_path / "m.py", DECLARED)
    tables = TextTables(tmp_path, lambda rel: source)
    assert source.tree is not None
    for old in ("save_model", "model", "save", "SaveModel", "x"):
        expected = sorted(
            ("m.py", name, span)
            for node in ast.walk(source.tree)
            if (name := declared_name(node)) is not None and (span := source.name_span(node)) is not None
            and is_compound(name, old)
        )
        assert tables.compounds(["m.py"], old) == expected, old


def test_compounds_come_only_from_the_files_asked_about(tmp_path: Path) -> None:
    texts = {"a.py": "def save_model_now() -> None:\n    pass\n", "b.py": "def save_model_now() -> None:\n    pass\n"}
    tables = TextTables(tmp_path, lambda rel: SourceFile(tmp_path / rel, texts[rel]))
    assert [rel for rel, _, _ in tables.compounds(["a.py"], "save")] == ["a.py"]
    assert [rel for rel, _, _ in tables.compounds(["b.py"], "save")] == ["b.py"]


def test_literals_leave_docstrings_and_fstring_parts(tmp_path: Path) -> None:
    text = '"""save_model"""\na = "save_model"\nb = f"save_model{a}"\nc = \'save_model\'\n'
    source = SourceFile(tmp_path / "m.py", text)
    spans = TextTables(tmp_path, lambda rel: source).literals("m.py")["save_model"]
    assert [text[s:e] for s, e in spans] == ['"save_model"', "'save_model'"]


# ---- the positions a run asks about

QUERIED = """import typing
from pkg import Model, check, deco


class Sub(Model, typing.Generic):
    field: list[Model]


@deco
def make() -> Model:
    return Model(columns=[1])


def f(m: Model) -> object:
    getattr(m, "columns")
    check("pkg.Model.columns")
    return m.model_validate({"columns": []}), print("unrelated")
"""


def _asked(text: str, names: set[str]) -> dict[str, set[str]]:
    source = SourceFile(Path("/p/q.py"), text)
    out: dict[str, set[str]] = {}
    for q in fact_queries(source, names):
        line = source.line(q.offset)
        word = _WORD.match(text, q.offset).group()  # pyright: ignore[reportOptionalMemberAccess]
        out.setdefault(f"{line}:{word}", set()).update(q.kinds)
    return out


def test_fact_queries_cover_classes_bases_annotations_decorators_sinks_and_string_members() -> None:
    asked = _asked(QUERIED, {"columns"})
    assert asked == {
        "5:Sub": {"class"},
        "5:Model": {"definition"},
        "5:Generic": {"definition"},
        "6:list": {"definition"},
        "6:Model": {"definition"},
        "9:deco": {"definition"},
        "11:Model": {"definition", "typeDefinition"},
        "11:columns": {"signature"},
        "14:object": {"definition"},
        "15:getattr": {"definition", "typeDefinition"},
        "15:m": {"verdict"},
        "16:check": {"definition"},
        "17:m": {"definition", "typeDefinition"},
        "17:model_validate": {"definition", "typeDefinition"},
    }


def test_a_file_that_does_not_parse_asks_nothing() -> None:
    assert fact_queries(SourceFile(Path("/p/bad.py"), "def (:\n"), {"x"}) == []


def test_candidates_hold_a_name_or_an_escaped_string_of_it(tmp_path: Path) -> None:
    texts = {"a.py": "x = save_model\n", "b.py": 'y = "s\\x61ve_model"\n', "c.py": 'z = "\\n"\n', "d.py": "w = 1\n"}
    found = candidate_files(sorted(texts), texts.__getitem__, lambda rel: SourceFile(tmp_path / rel, texts[rel]),
                            {"save_model"})
    assert found == ["a.py", "b.py"]


# ---- the fingerprint's interpreter fallback


@pytest.mark.skipif(sys.platform == "win32", reason="a POSIX shell script stands in for the interpreter")
def test_without_a_configured_venv_the_interpreters_search_paths_count(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    site = tmp_path / "site"
    site.mkdir()
    (site / "lib.py").write_text("x = 1\n", encoding="utf-8")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    info = json.dumps({"executable": "/fake/python3", "version": [3, 12, 0], "prefix": "/fake", "path": [str(site)]})
    script = bin_dir / "python3"
    script.write_text(f"#!/bin/sh\necho '{info}'\n", encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", str(bin_dir) + os.pathsep + os.environ["PATH"])
    project = tmp_path / "proj"
    project.mkdir()
    (project / "m.py").write_text("y = 2\n", encoding="utf-8")
    first = fingerprint(project)
    assert fingerprint(project) == first
    (site / "lib.py").write_text("x = 'changed'\n", encoding="utf-8")
    assert fingerprint(project) != first


@pytest.mark.parametrize("config", [
    {"extraPaths": ["../extra"]},
    {"executionEnvironments": [{"root": ".", "extraPaths": ["../extra"]}]},
    {"stubPath": "../extra"},
    {"typeshedPath": "../extra"},
])
def test_a_directory_the_checker_config_names_counts(tmp_path: Path, config: dict[str, object]) -> None:
    extra = tmp_path / "extra"
    extra.mkdir()
    (extra / "lib.py").write_text("x = 1\n", encoding="utf-8")
    project = tmp_path / "proj"
    project.mkdir()
    (project / "pyrightconfig.json").write_text(json.dumps(config), encoding="utf-8")
    first = fingerprint(project)
    (extra / "lib.py").write_text("x = 'changed'\n", encoding="utf-8")
    assert fingerprint(project) != first


@pytest.mark.parametrize(("text", "expected"), [
    ('{\n  // a comment\n  "a": 1, /* another */ "b": [1, 2,],\n}', {"a": 1, "b": [1, 2]}),
    ('{"url": "http://x//y", "s": "a,}/*b*/", "q": "\\"//"}', {"url": "http://x//y", "s": "a,}/*b*/", "q": '"//'}),
    ('{"a": 1 // trailing\n}', {"a": 1}),
])
def test_a_jsonc_config_reads_as_json(text: str, expected: dict[str, object]) -> None:
    assert json.loads(_jsonc(text)) == expected


@pytest.mark.parametrize("encoding", ["utf-8", "utf-8-sig"], ids=["plain", "bom"])
def test_an_extends_in_a_commented_config_counts(tmp_path: Path, encoding: str) -> None:
    base = tmp_path / "base.json"
    base.write_text('{"reportMissingImports": "none"}', encoding="utf-8")
    project = tmp_path / "proj"
    project.mkdir()
    (project / "pyrightconfig.json").write_text('{\n  // shared settings\n  "extends": "../base.json",\n}\n',
                                                encoding=encoding)
    first = fingerprint(project)
    base.write_text('{"reportMissingImports": "error"}', encoding="utf-8")
    assert fingerprint(project) != first


@pytest.mark.parametrize(("files", "used"), [
    ({"pyrightconfig.json": "{}", "pyproject.toml": '[tool.basedpyright]\nvenv = "v"\n'}, "pyrightconfig.json"),
    ({"pyproject.toml": '[tool.basedpyright]\nvenv = "v"\n'}, "pyproject.toml"),
], ids=["empty-json-wins", "toml-alone"])
def test_the_checker_reads_pyrightconfig_whenever_it_exists(tmp_path: Path, files: dict[str, str], used: str) -> None:
    for name, text in files.items():
        (tmp_path / name).write_text(text, encoding="utf-8")
    assert [p.name for p, _ in _config_chain(tmp_path)] == [used]
