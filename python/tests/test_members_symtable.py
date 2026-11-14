"""The Python member walker against stdlib `symtable`: every class-level binding form of a name is a declaration."""

from __future__ import annotations

import ast
import symtable
import sys
import textwrap
from pathlib import Path

import pytest

from living_architecture.refactor.members import member_declarations
from living_architecture.refactor.python_source import SourceFile

FORMS = {
    "def": "def save_model(self) -> None: ...",
    "async-def": "async def save_model(self) -> None: ...",
    "class": "class save_model: ...",
    "assign": "save_model = 1",
    "annotated": "save_model: int = 1",
    "annotated-bare": "save_model: int",
    "augmented": "save_model += 1",
    "tuple-target": "a, (b, save_model) = 1, (2, 3)",
    "starred-target": "a, *save_model = 1, 2",
    "for-target": "for save_model in range(2): ...",
    "with-as": "with open('f') as save_model: ...",
    "import-as": "import os as save_model",
    "import": "import save_model",
    "from-import": "from os import path as save_model",
    "walrus": "(save_model := 1)",
    "except-as": "try:\n    pass\nexcept Exception as save_model:\n    pass",
    "match-capture": "match 1:\n    case save_model: ...",
    "match-as": "match 1:\n    case int() as save_model: ...",
    "match-star": "match [1]:\n    case [*save_model]: ...",
    "match-rest": "match {}:\n    case {**save_model}: ...",
}
if sys.version_info >= (3, 12):
    FORMS["type-alias"] = "type save_model = int"

BLOCKS = {
    "direct": ("", "", 0),
    "if": ("if True:\n", "", 4),
    "try": ("try:\n", "\nexcept Exception:\n    pass", 4),
    "with": ("with open('f'):\n", "", 4),
    "for": ("for _ in ():\n", "", 4),
    "while": ("while False:\n", "", 4),
    "match": ("match 1:\n    case _:\n", "", 8),
}


def _class(form: str, block: str) -> str:
    head, tail, depth = BLOCKS[block]
    return "class C:\n" + textwrap.indent(head + textwrap.indent(form, " " * depth) + tail, "    ") + "\n"


def _symtable_binds(text: str) -> bool:
    table = next(t for t in symtable.symtable(text, "m.py", "exec").get_children() if t.get_name() == "C")
    try:
        symbol = table.lookup("save_model")
    except KeyError:
        return False
    return symbol.is_assigned() or symbol.is_imported() or symbol.is_namespace()


@pytest.mark.parametrize("block", BLOCKS)
@pytest.mark.parametrize("form", FORMS)
def test_every_class_level_binding_is_a_declaration(form: str, block: str) -> None:
    text = _class(FORMS[form], block)
    source = SourceFile(Path("/m.py"), text)
    assert source.tree is not None, text
    cls = next(n for n in ast.walk(source.tree) if isinstance(n, ast.ClassDef) and n.name == "C")
    found = member_declarations(cls, "save_model")
    assert _symtable_binds(text), text
    assert found, text
    for node in found:
        span = source.name_span(node)
        assert span is not None, (text, ast.dump(node))
        assert text[span[0] : span[1]] == "save_model", text


@pytest.mark.parametrize(
    ("body", "symtable_agrees"),
    [
        ("print(save_model)", True),
        ("def f(self) -> None:\n        save_model = 1", True),
        # PEP 709 inlines the comprehension into the class's table; its variable is still no class attribute.
        ("x = [save_model for save_model in ()]", sys.version_info < (3, 12)),
        ("def f(self, save_model: int) -> None: ...", True),
    ],
    ids=["read", "method-local", "comprehension", "parameter"],
)
def test_names_bound_elsewhere_are_not_declarations(body: str, symtable_agrees: bool) -> None:
    text = f"class C:\n    {body}\n"
    source = SourceFile(Path("/m.py"), text)
    assert source.tree is not None
    cls = next(n for n in ast.walk(source.tree) if isinstance(n, ast.ClassDef))
    assert _symtable_binds(text) is not symtable_agrees
    assert member_declarations(cls, "save_model") == []
