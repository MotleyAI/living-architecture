"""How a `**kwargs` carrier uses its `**kw` name, and the source text of parenthesised receivers."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from living_architecture.refactor.keyword_links import CarrierShape, keyword_sites
from living_architecture.refactor.member_scan import access_receiver, written_text
from living_architecture.refactor.python_source import SourceFile


def _shape(body: str, signature: str = "**kw") -> CarrierShape:
    source = SourceFile(Path("/p/c.py"), f"def f({signature}):\n" + "".join(f"    {line}\n" for line in body.splitlines()))
    (fn,) = [n for n in source.of_type(ast.FunctionDef) if n.name == "f"]
    return CarrierShape(source, fn)


@pytest.mark.parametrize("body", [
    "return X(**kw)",
    "return X.model_construct(**kw), X.model_validate(kw), x.model_copy(update=kw), X.model_validate(obj=kw)",
    "return X(**{'a': 1, **kw})",
    "data = {'a': 1, **kw}\nreturn X(**data), X.model_validate(data)",
    "if kw and not kw and len(kw) > 1:\n    pass\nwhile kw:\n    assert kw\nreturn 1 if kw else 0",
    "return [kw for kw in 'ab'], (lambda kw: kw)(1), X(**kw)",
    "def inner(kw):\n    return kw\nreturn inner(1)",
])
def test_sinks_key_forms_and_neutral_uses_leave_a_carrier_resolved(body: str) -> None:
    assert _shape(body).resolved


def test_each_sink_is_filed_with_its_call() -> None:
    shape = _shape("data = {**kw}\nreturn X(**kw), X.model_validate(kw), Y(**data)")
    assert sorted((kind, ast.unparse(call.func)) for kind, call in shape.sinks) == [
        ("call", "X"), ("call", "Y"), ("keyed", "X.model_validate")]


def test_key_forms_are_filed_with_their_strings() -> None:
    shape = _shape("kw['a'] = kw.get('b') or kw.pop('c', None) or kw.setdefault('d', 1)\ndel kw['e']\nreturn 'f' in kw, 'g' not in kw")
    assert shape.resolved
    assert sorted(str(key.value) for key in shape.keys) == list("abcdefg")


@pytest.mark.parametrize("body", [
    "d = kw\nreturn X(**d)",
    "return X(**dict(kw))",
    "return X(**kw.copy())",
    "base.update(kw)",
    "return base | kw",
    "return build(kw)",
    "return build(extra=kw)",
    "return kw",
    "for k in kw:\n    pass",
    "return kw.items(), kw.keys(), kw.values()",
    "return kw[name]",
    "return kw.get(name)",
    "return name in kw",
    "kw = {}\nreturn X(**kw)",
    "del kw",
    "def inner():\n    return X(**kw)\nreturn inner()",
    "return [k for k in kw]",
    "return [X(**kw) for _ in range(2)]",
    "return (lambda kw=kw: kw)()",
    "data = {**kw}\nprint(data)\nreturn X(**data)",
    "data = {**kw}\ndata = {}\nreturn X(**data)",
    "return {'a': kw}",
    "return X(**(kw or {}))",
])
def test_any_other_use_makes_a_carrier_unresolved(body: str) -> None:
    assert not _shape(body).resolved


def test_keyword_sites_are_keywords_and_plain_constant_keys_of_unpacked_literals() -> None:
    text = "f(old=1, **{'old': 2, 'other': 3})\ng()(old=4)\nf(**{'ol' 'd': 5})\nf(**data)\n"
    source = SourceFile(Path("/p/s.py"), text)
    found = [(text[s.span[0] : s.span[1]], s.line, s.keyword, s.query) for s in keyword_sites(source, "old")]
    assert found == [("old", 1, True, 2), ("old", 1, False, 0), ("old", 2, True, text.index("old=4"))]
    assert keyword_sites(source, "old")[1].span[0] == text.index("'old'") + 1


@pytest.mark.parametrize(("text", "expected"), [
    ("x.old", "x"),
    ("(a or b).old", "(a or b)"),
    ("((a\n   or b)).old", "((a or b))"),
    ("(\n    m\n).old", "( m )"),
    ("f(x).old", "f(x)"),
    ("g((a or b).old)", "(a or b)"),
])
def test_an_access_receiver_keeps_the_parentheses_written_around_it(text: str, expected: str) -> None:
    source = SourceFile(Path("/p/r.py"), text + "\n")
    (access,) = [n for n in source.of_type(ast.Attribute) if n.attr == "old"]
    assert access_receiver(source, access) == expected


def test_written_text_stops_at_its_left_bound() -> None:
    text = "getattr((a or b), 'x')\ngetattr(m, 'x')\n"
    source = SourceFile(Path("/p/w.py"), text)
    first, second = (call.args[0] for call in source.of_type(ast.Call))
    assert written_text(source, first, text.index("(") + 1) == "(a or b)"
    assert written_text(source, second, text.index("(", text.index("\n")) + 1) == "m"
