"""A source's identifier spans follow Python's reading of identifiers: NFKC-normalized, combining marks included."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from deterministic_refactor.refactor.python_source import SourceFile, every_parameter, header_end

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


def test_the_all_strings_are_the_names_all_exports() -> None:
    text = (
        '__all__: list[str] = ["a", ("b")]\n__all__ += ("c",)\n__all__.append("d")\n__all__.extend(["e"])\n'
        '__all__ = ["f"] + build("g")\n__all__.extend("i")\n__all__ += "j"\n'
        '__all__ = build(["k"]) + [f(x) for x in ["l"]]\nother = ["h"]\n'
    )
    source = SourceFile(Path("m.py"), text)
    assert [n.value for n in source.all_strings()] == ["a", "b", "c", "d", "e", "f"]


@pytest.mark.parametrize("text", ["def f(a, /, b=1, *c, d, e=2, **g): pass\n", "lambda a, /, b=1, *c, d, e=2, **g: 0\n"],
                         ids=["def", "lambda"])
def test_every_parameter_is_listed_in_declaration_order(text: str) -> None:
    node = next(n for n in ast.walk(ast.parse(text)) if isinstance(n, (ast.FunctionDef, ast.Lambda)))
    assert [a.arg for a in every_parameter(node.args)] == ["a", "b", "c", "d", "e", "g"]


@pytest.mark.parametrize(("text", "header"), [
    ("#!/usr/bin/env python\n# coding: latin-1\nX = 1\n", "#!/usr/bin/env python\n# coding: latin-1\n"),
    ("# coding: latin-1\n# note\n", "# coding: latin-1\n"),
    ("\n# coding: latin-1\nX = 1\n", "\n# coding: latin-1\n"),
    ("#!/usr/bin/env python\nX = 1\n", "#!/usr/bin/env python\n"),
    ("X = 1\n# coding: latin-1\n", ""),
    ("# note\nX = 1\n", ""),
    ("", ""),
], ids=["shebang-and-coding", "coding-first", "coding-below-blank", "shebang-only", "coding-below-code", "comment", "empty"])
def test_the_header_is_the_shebang_and_the_coding_declaration(text: str, header: str) -> None:
    assert text[: header_end(text)] == header

