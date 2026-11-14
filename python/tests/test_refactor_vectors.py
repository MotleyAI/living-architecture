"""`shared/vectors/refactor-text.yaml` through the Python twin's text primitives."""

from __future__ import annotations

import ast
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml

from living_architecture.cli import dr_refactor
from living_architecture.refactor.mentions import mentions, qualifier_segments, source_regions
from living_architecture.refactor.python_source import SourceFile, split_lines
from living_architecture.refactor.rope_refactor import _kept_lines  # pyright: ignore[reportPrivateUsage]
from living_architecture.refactor.sites import Site

VECTORS: dict[str, Any] = yaml.safe_load(
    (next(p for p in Path(__file__).resolve().parents if (p / "shared").is_dir()) / "shared/vectors/refactor-text.yaml")
    .read_text(encoding="utf-8")
)


def _expected(vector: dict[str, Any], key: str) -> Any:
    return vector.get("python", {}).get(key, vector[key])


@pytest.mark.parametrize("vector", VECTORS["lines"], ids=lambda v: v["name"])
def test_lines(vector: dict[str, Any]) -> None:
    source = SourceFile(Path("a.py"), vector["text"])
    assert [source.line(o) for o in vector["offsets"]] == _expected(vector, "lines")
    assert len(split_lines(vector["text"])) == _expected(vector, "count")
    assert "".join(split_lines(vector["text"])) == vector["text"]


@pytest.mark.parametrize("vector", VECTORS["mentions"], ids=lambda v: v["name"])
def test_mentions(vector: dict[str, Any]) -> None:
    text = vector["text"]
    regions = iter([(s, e, "string", False) for s, e in vector.get("regions", [[0, len(text)]])])
    assert [m.start for m in mentions(text, vector["old"], regions, lambda _: 1)] == _expected(vector, "starts")


@pytest.mark.parametrize("vector", VECTORS["qualifiers"], ids=lambda v: v["name"])
def test_qualifiers(vector: dict[str, Any]) -> None:
    assert qualifier_segments(vector["text"], vector["at"]) == _expected(vector, "segments")


@pytest.mark.parametrize("vector", VECTORS["sites"], ids=lambda v: v["name"])
def test_sites(vector: dict[str, Any], tmp_path: Path) -> None:
    root = (tmp_path / "project").resolve()
    root.mkdir()
    for rel in vector["files"]:
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text("")
    site = Site.parse(vector["site"], root, base=root)
    assert [[path, line, site.covers(path, line)] for path, line, _ in vector["checks"]] == vector["checks"]


# ---- the line index's users


def test_line_locator_counts_python_lines_only(typed_project: Callable[..., Path], capsys: pytest.CaptureFixture[str]) -> None:
    root = typed_project({"pkg/m.py": "x = 1  # a\fb\ndef old() -> None:\n    pass\n"})
    assert dr_refactor(["--project", str(root), "rename", "--file", str(root / "pkg/m.py"), "--line", "2", "--col", "5",
                        "--new-name", "new"]) == 0
    assert "-def old() -> None:\n+def new() -> None:" in capsys.readouterr().out


def test_docs_regions_in_a_cr_only_file() -> None:
    text = "x = 1\r# calls save_model\ry = 'save_model'\r"
    found = mentions(text, "save_model", source_regions(SourceFile(Path("a.py"), text)), lambda _: 1)
    assert [(m.start, m.where) for m in found] == [(text.index("save_model"), "comment"), (text.rindex("save_model"), "string")]


def test_a_kept_line_counts_python_lines_only() -> None:
    old, new = "a\fb = 1\nc = 1\n", "a\fB = 1\nc = 1\n"
    assert _kept_lines("a.py", old, new, lambda _, line: line == 1) == old


@pytest.mark.parametrize(
    "text",
    ["x = 'save_model'", "if x:\n    y = 'save_model'", "class A:\n    def f(self):\n        return 'save_model'"],
    ids=["no-final-newline", "dedent-at-eof", "nested-dedents-at-eof"],
)
def test_docs_regions_ignore_synthetic_end_tokens(text: str) -> None:
    found = mentions(text, "save_model", source_regions(SourceFile(Path("a.py"), text)), lambda _: 1)
    assert [m.start for m in found] == [text.index("save_model")]


def test_an_except_binding_is_located_after_its_type() -> None:
    text = 'try:\n    pass\nexcept errors["as save_model"] as save_model:\n    pass\n'
    source = SourceFile(Path("a.py"), text)
    assert source.tree is not None
    handler = next(n for n in ast.walk(source.tree) if isinstance(n, ast.ExceptHandler))
    assert source.name_span(handler) == (text.rindex("save_model"), text.rindex("save_model") + len("save_model"))
