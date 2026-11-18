"""How a `**kwargs` carrier uses its `**kw` name, the signature proof of a renamed parameter, and the source text of
parenthesised receivers."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from living_architecture.refactor.keyword_links import CarrierShape, keyword_sites, renamed_names
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
    "def inner():\n    kw = {}\n    return kw\nreturn X(**kw), inner()",
    "def inner():\n    import kw\n    return kw\nreturn X(**kw), inner()",
    "class C:\n    kw = 1\n    twice = kw\nreturn X(**kw)",
    "class C:\n    kw = {'a': 1}\n    def get(self, value=kw['a']):\n        return value\nreturn X(**kw)",
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
    "from defaults import payload as kw\nreturn X(**kw)",
    "import kw\nreturn X(**kw)",
    "try:\n    pass\nexcept E as kw:\n    pass\nreturn X(**kw)",
    "match v:\n    case {**kw}:\n        pass\nreturn X(**kw)",
    "match v:\n    case [*kw]:\n        pass\nreturn X(**kw)",
    "def kw():\n    pass\nreturn X(**kw)",
    "class C:\n    kw = 1\n    def m(self):\n        return kw\nreturn X(**kw)",
    "class C(Base[kw]):\n    kw = 1\nreturn X(**kw)",
    "class C:\n    seen = kw\nreturn X(**kw)",
    "def inner(x: kw):\n    kw = {}\n    return kw\nreturn X(**kw)",
    "def inner() -> kw:\n    kw = {}\n    return kw\nreturn X(**kw)",
    "def inner():\n    nonlocal kw\n    kw = {}\nreturn X(**kw), inner()",
    "data = {**kw}\nmatch v:\n    case {**data}:\n        pass\nreturn X(**data)",
])
def test_any_other_use_makes_a_carrier_unresolved(body: str) -> None:
    assert not _shape(body).resolved


def test_literal_keys_and_measuring_callees_are_filed() -> None:
    shape = _shape("data = {'a': 1, **kw}\nreturn X(**data), X(**{'b': 2, **kw}), len(kw)")
    assert shape.resolved
    assert (sorted(shape.literal_keys), [name.id for name in shape.measures]) == (["a", "b"], ["len"])


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
    ("(# receiver\n    m).old", "(# receiver m)"),
    ("(m  # receiver\n).old", "(m # receiver )"),
    ("('#', m)[1].old", "('#', m)[1]"),
    ("(m \\\n).old", "(m \\ )"),
    ("( \\\n m).old", "( \\ m)"),
    ("# header\r(m # receiver\r).old", "(m # receiver )"),
])
def test_an_access_receiver_keeps_the_parentheses_written_around_it(text: str, expected: str) -> None:
    source = SourceFile(Path("/p/r.py"), text + ("\r" if "\r" in text else "\n"))
    (access,) = [n for n in source.of_type(ast.Attribute) if n.attr == "old"]
    assert access_receiver(source, access) == expected


def test_written_text_stops_at_its_left_bound() -> None:
    text = "getattr((a or b), 'x')\ngetattr(m, 'x')\n"
    source = SourceFile(Path("/p/w.py"), text)
    first, second = (call.args[0] for call in source.of_type(ast.Call))
    assert written_text(source, first, text.index("(") + 1) == "(a or b)"
    assert written_text(source, second, text.index("(", text.index("\n")) + 1) == "m"


@pytest.mark.parametrize(("run", "before", "after", "expected"), [
    ({("old", "new")}, ("a", "old"), ("a", "new"), True),
    ({("old", "new"), ("count", "total")}, ("old", "count"), ("new", "total"), True),
    ({("old", "new"), ("new", "other")}, ("old", "new"), ("new", "other"), True),
    ({("old", "new"), ("new", "old")}, ("old", "new"), ("new", "old"), True),
    ({("old", "new")}, ("old", "count"), ("new", "total"), False),
    ({("old", "new")}, ("a", "old"), ("a", "old"), False),
    ({("old", "new")}, ("a", "old"), ("new", "a"), False),
    ({("old", "new")}, ("a", "old"), ("a", "new", "b"), False),
])
def test_a_renamed_signature_changes_only_by_the_runs_parameter_renames(
    run: set[tuple[str, str]], before: tuple[str, ...], after: tuple[str, ...], expected: bool
) -> None:
    assert renamed_names(frozenset(run), before, after, ("old", "new")) is expected
