"""A source's identifier spans follow Python's reading of identifiers: NFKC-normalized, combining marks included."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from living_architecture.refactor.python_source import SourceFile

LIGATURE = "\ufb01x"  # NFKC: "fix", one character longer
COMBINING = "a\u0301b"  # NFKC: one precomposed letter, then "b"


@pytest.mark.parametrize(
    ("text", "kind", "raw"),
    [
        ("o.fix\n", ast.Attribute, "fix"),
        (f"o.{LIGATURE}\n", ast.Attribute, LIGATURE),
        (f"def g({LIGATURE}): pass\n", ast.arg, LIGATURE),
        (f"f({LIGATURE}=1)\n", ast.keyword, LIGATURE),
        (f"def {LIGATURE}(): pass\n", ast.FunctionDef, LIGATURE),
        (f"class {COMBINING}: pass\n", ast.ClassDef, COMBINING),
        (f"import os as {COMBINING}\n", ast.alias, COMBINING),
        (f"try:\n    pass\nexcept OSError as {LIGATURE}:\n    pass\n", ast.ExceptHandler, LIGATURE),
        (f"match 1:\n    case {COMBINING}:\n        pass\n", ast.MatchAs, COMBINING),
    ],
    ids=["ascii-attribute", "attribute", "arg", "keyword", "def", "class", "import-as", "except-as", "match-capture"],
)
def test_the_name_span_covers_the_identifier_as_written(text: str, kind: type[ast.AST], raw: str) -> None:
    source = SourceFile(Path(), text)
    assert source.tree is not None
    node = next(n for n in ast.walk(source.tree) if isinstance(n, kind))
    span = source.name_span(node)
    assert span is not None
    assert source.text[span[0] : span[1]] == raw


def test_a_word_is_matched_whole_and_by_its_normal_form() -> None:
    source = SourceFile(Path(), f"fixed {LIGATURE} fix\n")
    assert source.word(0, len(source.text), "fix") == (6, 8)
    assert source.word(0, len(source.text), "fix", last=True) == (9, 12)
