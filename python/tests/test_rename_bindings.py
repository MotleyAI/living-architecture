"""Python `dr-refactor rename` keeps every reference's binding: Python's own scoping, star imports, the edits that take
part, the finding site, the check order and the implicit root's members."""

from __future__ import annotations

import ast
import gc
import importlib.util
import re
import symtable
import sys
import textwrap
import weakref
from collections.abc import Callable
from pathlib import Path

import pytest
from project_files import file_tree
from refactor_cli import readouterr

from living_architecture.cli.dr_refactor import dr_refactor
from living_architecture.contract import language, message
from living_architecture.refactor import bindings
from living_architecture.refactor.bindings import BindingCheck, Conflict, EntryEdits, module_binding
from living_architecture.refactor.python_source import SourceFile
from living_architecture.refactor.text_edits import TextEdit

MakeProject = Callable[..., Path]
NEW = "fresh"


def _rename(root: Path, rel: str, offset: int, new_name: str = NEW, *flags: str) -> int:
    return dr_refactor(["--project", str(root), "--apply", "rename", "--file", str(root / rel), "--offset", str(offset),
                        "--new-name", new_name, *flags])


def _at(text: str, needle: str, nth: int = 0) -> int:
    offset = -1
    for _ in range(nth + 1):
        offset = text.index(needle, offset + 1)
    return offset


def _conflict(name: str, path: str, line: int) -> tuple[str, str]:
    return "", message("refactor.name-conflict", name=name, path=path, line=line) + "\n"


def _one(check: BindingCheck, entries: list[EntryEdits]) -> list[Conflict]:
    """The conflicts of a one-pass plan."""
    [found] = check.conflicts([entries])
    return found


def _refused(root: Path, rel: str, offset: int, capsys: pytest.CaptureFixture[str], site: tuple[str, int],
             new_name: str = NEW, *flags: str) -> None:
    before = file_tree(root)
    assert _rename(root, rel, offset, new_name, *flags) == 1
    assert readouterr(capsys) == _conflict(new_name, *site)
    assert file_tree(root) == before


# --- Python's own scoping decides, as symtable reports it ----------------------------------------------------------

FORMS = {
    "assign": "fresh = 1",
    "annotated": "fresh: int = 1",
    "annotated-bare": "fresh: int",
    "augmented": "fresh += 1",
    "tuple-target": "a, (b, fresh) = 1, (2, 3)",
    "starred-target": "a, *fresh = 1, 2",
    "for-target": "for fresh in range(2): ...",
    "with-as": "with open('f') as fresh: ...",
    "import": "import fresh",
    "import-as": "import os as fresh",
    "from-import": "from os import path as fresh",
    "walrus": "(fresh := 1)",
    "except-as": "try:\n    pass\nexcept Exception as fresh:\n    pass",
    "match-capture": "match 1:\n    case fresh: ...",
    "match-as": "match 1:\n    case int() as fresh: ...",
    "match-star": "match [1]:\n    case [*fresh]: ...",
    "match-rest": "match {}:\n    case {**fresh}: ...",
    "def": "def fresh() -> None: ...",
    "async-def": "async def fresh() -> None: ...",
    "class": "class fresh: ...",
    "del": "del fresh",
    "global": "global fresh\nfresh = 1",
    "lambda-parameter": "g = lambda fresh: fresh",
    "nested-parameter": "def g(fresh: int) -> int:\n    return fresh",
    "nested-local": "def g() -> int:\n    fresh = 1\n    return fresh",
}
if sys.version_info >= (3, 12):
    FORMS["type-alias"] = "type fresh = int"
    FORMS["type-parameter"] = "def g[fresh]() -> None: ..."


ENCLOSED_FORMS = {
    "nonlocal": "nonlocal fresh",
    "global": "global fresh",
    "global-assigned": "global fresh\nfresh = 1",
}


def _module(form: str) -> str:
    return "old = 1\n\n\ndef f() -> object:\n" + textwrap.indent(form, "    ") + "\n    return old\n"


def _enclosed(form: str) -> str:
    """`f` nested in a function binding `fresh`."""
    inner = "def f() -> object:\n" + textwrap.indent(form, "    ") + "\n    return old\n"
    return "old = 1\n\n\ndef outer() -> object:\n    fresh = 0\n\n" + textwrap.indent(inner, "    ") + "\n    return f\n"


def _table(table: symtable.SymbolTable, name: str) -> symtable.SymbolTable | None:
    if table.get_name() == name:
        return table
    return next((found for child in table.get_children() if (found := _table(child, name)) is not None), None)


def _rebinds(edited: str) -> bool:
    """Python's own answer: after the rename, `f`'s read of `fresh` is not the module-level name renamed, or the
    module already bound `fresh`."""
    f = _table(symtable.symtable(edited, "m.py", "exec"), "f")
    assert f is not None
    try:
        symbol = f.lookup(NEW)
    except KeyError:
        return False
    return symbol.is_local() or symbol.is_free() or (symbol.is_declared_global() and symbol.is_assigned())


@pytest.mark.parametrize(
    "text",
    [*(pytest.param(_module(form), id=key) for key, form in FORMS.items()),
     *(pytest.param(_enclosed(form), id=f"enclosed-{key}") for key, form in ENCLOSED_FORMS.items())],
)
def test_a_binding_form_conflicts_exactly_when_python_rebinds_the_read(
    typed_project: MakeProject, capsys: pytest.CaptureFixture[str], text: str
) -> None:
    root = typed_project({"pkg/m.py": text})
    before = file_tree(root)
    code = _rename(root, "pkg/m.py", 0)
    out, err = readouterr(capsys)
    if _rebinds(text.replace("old", NEW)):
        prefix, suffix = message("refactor.name-conflict", name=NEW, path="pkg/m.py", line=424242).split("424242")
        assert (code, out, err.startswith(prefix), err.endswith(suffix + "\n")) == (1, "", True, True), err
        assert file_tree(root) == before
    else:
        assert (code, err) == (0, ""), err
        assert (root / "pkg/m.py").read_text(encoding="utf-8") == text.replace("old", NEW)


def test_a_comprehension_target_binds_no_name_of_the_function(typed_project: MakeProject) -> None:
    """From 3.12 symtable reports an inlined comprehension's target as the function's own (PEP 709); it is not."""
    text = _module("xs = [fresh for fresh in range(2)]")
    root = typed_project({"pkg/m.py": text})
    assert _rename(root, "pkg/m.py", 0) == 0
    assert (root / "pkg/m.py").read_text(encoding="utf-8") == text.replace("old", NEW)


# --- members of every kind -----------------------------------------------------------------------------------------

METHOD = "\n    def old(self) -> int:\n        return 1\n"


@pytest.mark.parametrize(
    ("text", "line"),
    [
        ("class C:\n    fresh: int = 0\n" + METHOD, 2),
        ("class C:\n    @property\n    def fresh(self) -> int:\n        return 0\n" + METHOD, 3),
        ("from dataclasses import dataclass\n\n\n@dataclass\nclass C:\n    fresh: int\n" + METHOD, 6),
        ("from pydantic import BaseModel\n\n\nclass C(BaseModel):\n    fresh: int\n" + METHOD, 5),
    ],
    ids=["annotated-field", "property", "dataclass-field", "pydantic-field"],
)
def test_a_method_renamed_onto_a_member_of_any_kind_is_refused(
    typed_project: MakeProject, capsys: pytest.CaptureFixture[str], text: str, line: int
) -> None:
    root = typed_project({"pkg/m.py": text})
    _refused(root, "pkg/m.py", _at(text, "def old") + len("def "), capsys, ("pkg/m.py", line))


# --- star imports bind the source module's public names ------------------------------------------------------------

STAR_USER = "from pkg.s import *\n\nold = 1\nprint(old)\n"


@pytest.mark.parametrize(
    ("source", "new_name", "refused"),
    [
        ('fresh = 2\nother = 3\n__all__ = ["other"]\n', NEW, False),
        ('fresh = 2\nother = 3\n__all__ = ("other",)\n', NEW, False),
        ('fresh = 2\n__all__ = ["fresh"]\n', NEW, True),
        ("fresh = 2\n", NEW, True),
        ('fresh = 2\nother = 3\n__all__ = ["other"] + []\n', NEW, True),
        ("_fresh = 2\n", "_fresh", False),
    ],
    ids=["all-list-omits", "all-tuple-omits", "all-lists", "no-all", "all-not-literal", "private"],
)
def test_a_star_import_binds_the_public_names(
    typed_project: MakeProject, capsys: pytest.CaptureFixture[str], source: str, new_name: str, refused: bool
) -> None:
    root = typed_project({"pkg/s.py": source, "pkg/c.py": STAR_USER})
    if refused:
        _refused(root, "pkg/c.py", _at(STAR_USER, "old"), capsys, ("pkg/c.py", 1), new_name)
    else:
        assert _rename(root, "pkg/c.py", _at(STAR_USER, "old"), new_name) == 0
        assert (root / "pkg/c.py").read_text(encoding="utf-8") == STAR_USER.replace("old", new_name)


def test_a_module_the_rename_does_not_edit_is_checked(
    typed_project: MakeProject, capsys: pytest.CaptureFixture[str]
) -> None:
    root = typed_project({"pkg/a.py": "old = 1\nprint(old)\n", "pkg/z.py": "from pkg.a import *\n\nfresh = 2\n"})
    _refused(root, "pkg/a.py", 0, capsys, ("pkg/z.py", 3))


# NFKC folds this spelling to `fresh`: a source spelling the name only so is still checked.
FULLWIDTH = "\uff46\uff52\uff45\uff53\uff48"


def test_a_module_spelling_the_new_name_in_another_normal_form_is_checked(
    typed_project: MakeProject, capsys: pytest.CaptureFixture[str]
) -> None:
    user = f"from pkg.other import *\nfrom pkg.a import *\n\nv = {FULLWIDTH}\n"
    root = typed_project({"pkg/other.py": "fresh = 0\n", "pkg/a.py": "old = 1\n", "pkg/z.py": user})
    _refused(root, "pkg/a.py", 0, capsys, ("pkg/z.py", 4))


def test_a_descendant_declaring_the_new_name_in_another_normal_form_is_checked(
    typed_project: MakeProject, capsys: pytest.CaptureFixture[str]
) -> None:
    text = "class C:\n    def old(self) -> int:\n        return 1\n"
    sub = f"from pkg.m import C\n\n\nclass D(C):\n    def {FULLWIDTH}(self) -> int:\n        return 2\n"
    root = typed_project({"pkg/m.py": text, "pkg/d.py": sub})
    _refused(root, "pkg/m.py", _at(text, "old"), capsys, ("pkg/d.py", 5))


@pytest.mark.parametrize("statement", ["import os as {}", "from os import sep as {}", "try:\n    pass\nexcept OSError as {}:\n    pass"],
                         ids=["import-as", "from-import-as", "except-as"])
def test_a_binding_in_another_normal_form_is_found(statement: str) -> None:
    text = statement.format(FULLWIDTH) + "\n"
    assert module_binding(text, "fresh") == text.index(FULLWIDTH)


def test_a_new_name_in_another_normal_form_is_checked_as_python_reads_it(
    typed_project: MakeProject, capsys: pytest.CaptureFixture[str]
) -> None:
    text = "old = 1\nfresh = 2\nprint(old, fresh)\n"
    root = typed_project({"pkg/m.py": text})
    _refused(root, "pkg/m.py", 0, capsys, ("pkg/m.py", 2), FULLWIDTH)


def test_a_member_renamed_onto_a_member_in_another_normal_form_is_refused(
    typed_project: MakeProject, capsys: pytest.CaptureFixture[str]
) -> None:
    text = "class C:\n    def old(self) -> int:\n        return 1\n\n    def fresh(self) -> int:\n        return 2\n"
    root = typed_project({"pkg/m.py": text})
    _refused(root, "pkg/m.py", _at(text, "old"), capsys, ("pkg/m.py", 5), FULLWIDTH)


def test_an_old_name_in_another_normal_form_is_checked_as_python_reads_it() -> None:
    old = "\uff4f\uff4c\uff44"  # NFKC: "old"
    text = f"{old} = 1\n\n\ndef f() -> int:\n    fresh = 2\n    return {old} + fresh\n"
    edits = [TextEdit(path="pkg/m.py", start=i, end=i + len(old), new_text="fresh")
             for i in (text.index(old), text.rindex(old))]
    check = BindingCheck(["pkg/__init__.py", "pkg/m.py"], [""], lambda rel: SourceFile(Path(rel), text if rel == "pkg/m.py" else ""))
    assert _one(check, [EntryEdits(index=1, new_name="fresh", edits=edits)]) == [Conflict(site=("pkg/m.py", text.index("fresh")), name="fresh")]


def test_a_conflict_names_the_entry_whose_new_name_it_spells_in_another_normal_form() -> None:
    text = "a = 0\nold = 1\nprint(fresh)\n"
    entries = [
        EntryEdits(index=1, new_name="other", edits=[TextEdit(path="pkg/m.py", start=0, end=1, new_text="other")]),
        EntryEdits(index=2, new_name=FULLWIDTH, edits=[TextEdit(path="pkg/m.py", start=6, end=9, new_text=FULLWIDTH)]),
    ]
    check = BindingCheck(["pkg/m.py"], [""], lambda rel: SourceFile(Path(rel), text))
    assert _one(check, entries) == [Conflict(site=("pkg/m.py", text.index("fresh")), name=FULLWIDTH)]


def test_a_module_renamed_onto_a_package_binding_in_another_normal_form_is_refused(
    typed_project: MakeProject, capsys: pytest.CaptureFixture[str]
) -> None:
    use = "from pkg import a\n\nprint(a.x)\n"
    root = typed_project({"pkg/__init__.py": "fresh = 1\n", "pkg/a.py": "x = 1\n", "pkg/use.py": use})
    _refused(root, "pkg/use.py", use.index("a\n"), capsys, ("pkg/__init__.py", 1), FULLWIDTH)


@pytest.mark.parametrize(
    ("body", "refused"),
    [
        ("    total = old\n    next = 2\n", False),
        ("    total = old\n    for _ in ():\n        next = 2\n", False),
        ("    def m(self) -> None:\n        next = 2\n\n    total = old\n", False),
        ("    for _ in [old]:\n        next = 2\n", False),
        ("    next = old\n", False),
        ("    next: int\n    total = old\n", False),
        ("    d = {}\n    next, d[old] = 1, 2\n", True),
        ("    for next in [old]:\n        pass\n", False),
        ("    with open(old) as next:\n        pass\n", False),
        ("    with open('a') as next, open(old):\n        pass\n", True),
        ("    (next := 1)\n    total = old\n", True),
        ("    match 1:\n        case next if old:\n            pass\n", True),
        ("    while False:\n        pass\n    else:\n        total = old\n        next = 2\n", False),
        ("    while True:\n        total = old\n        next = 2\n        break\n", True),
        ("    try:\n        pass\n    except OSError:\n        for _ in ():\n            total = old\n            next = 2\n", True),
    ],
    ids=["after", "loop-holds-only-the-binding", "method-binding", "for-iterable", "assignment-value", "annotation-only", "later-target", "for-target", "with-target", "with-later-item", "walrus", "case-guard", "while-else", "while", "loop-in-except"],
)
def test_a_class_body_read_sees_the_class_binding_only_once_it_may_have_run(body: str, refused: bool) -> None:
    text = "old = 1\n\n\nclass C:\n" + body
    edits = [TextEdit(path="pkg/m.py", start=m.start(), end=m.end(), new_text="next") for m in re.finditer(r"\bold\b", text)]
    check = BindingCheck(["pkg/m.py"], [""], lambda rel: SourceFile(Path(rel), text))
    assert bool(_one(check, [EntryEdits(index=1, new_name="next", edits=edits)])) is refused


def test_an_augmented_class_body_target_reads_before_it_binds() -> None:
    text = "old = 0\nnext = 5\n\n\nclass C:\n    old += 1\n"
    at = text.rindex("old")
    check = BindingCheck(["pkg/m.py"], [""], lambda rel: SourceFile(Path(rel), text))
    edits = [TextEdit(path="pkg/m.py", start=at, end=at + 3, new_text="next")]
    assert _one(check, [EntryEdits(index=1, new_name="next", edits=edits)])


SLIM = 'from os import *\n\nold = 1\n\n\nclass C:\n    for _ in ():\n        pass\n    x: "C"\n\n\ndef f(y: "C") -> int:\n    return old\n'


@pytest.mark.parametrize("state", ["before", "after"])
def test_a_parsed_module_keeps_no_syntax_tree(monkeypatch: pytest.MonkeyPatch, state: str) -> None:
    refs: list[weakref.ref[ast.AST]] = []
    real = bindings._Parsed.__init__

    def recording(self: bindings._Parsed, source: SourceFile, tree: ast.Module, *args: object) -> None:
        refs.extend(weakref.ref(node) for node in ast.walk(tree))
        real(self, source, tree, *args)  # pyright: ignore[reportArgumentType]

    monkeypatch.setattr(bindings._Parsed, "__init__", recording)
    check = BindingCheck(["pkg/m.py"], [""], lambda rel: SourceFile(Path(rel), SLIM))
    at = SLIM.index("old")
    edits = (TextEdit(path="pkg/m.py", start=at, end=at + 3, new_text=NEW),)
    parsed = check._analyse_before("pkg/m.py") if state == "before" else check._state("pkg/m.py", "pkg/m.py", edits)[0]
    gc.collect()
    assert parsed is not None
    assert refs
    assert [type(node).__name__ for ref in refs if (node := ref()) is not None] == []


# --- only resolver-backed edits take part --------------------------------------------------------------------------

KEYWORD = "def f(*, old: int) -> int:\n    return old\n\n\ndef caller() -> int:\n    fresh = 2\n    return f(old=fresh)\n"
STRING_MEMBER = (
    "class C:\n    old: int = 1\n\n\n"
    "def g(c: C) -> int:\n    fresh = 2\n    return getattr(c, \"old\") + fresh\n"
)
DICT_KEY = (
    "from typing import TypedDict\n\n\nclass TD(TypedDict):\n    old: int\n\n\n"
    "def g() -> int:\n    fresh = 2\n    d: TD = {\"old\": fresh}\n    return len(d)\n"
)


@pytest.mark.parametrize("text", [KEYWORD, STRING_MEMBER, DICT_KEY], ids=["call-keyword", "string-member", "dict-key"])
def test_an_edit_outside_name_resolution_beside_a_local_of_the_new_name_is_no_conflict(
    typed_project: MakeProject, text: str
) -> None:
    root = typed_project({"pkg/m.py": text})
    assert _rename(root, "pkg/m.py", _at(text, "old")) == 0
    assert (root / "pkg/m.py").read_text(encoding="utf-8") == text.replace("old", NEW)


# --- the finding site ----------------------------------------------------------------------------------------------

CAPTURING_USER = (
    "from pkg.m import old\n\n\n"
    "def f() -> int:\n    fresh = 1\n    return old + fresh\n\n\n"
    "def g() -> int:\n    fresh = 2\n    return old + fresh\n"
)


def test_the_first_site_by_path_then_offset_is_named(
    typed_project: MakeProject, capsys: pytest.CaptureFixture[str]
) -> None:
    root = typed_project({"pkg/m.py": "old = 1\n", "pkg/z_use.py": CAPTURING_USER, "pkg/a_use.py": CAPTURING_USER})
    _refused(root, "pkg/m.py", 0, capsys, ("pkg/a_use.py", 5))


def test_the_site_is_named_in_the_code_before_a_module_rename(
    typed_project: MakeProject, capsys: pytest.CaptureFixture[str]
) -> None:
    text = "from pkg import a\n\nb = 1\nX = a\n"
    root = typed_project({"pkg/a.py": text})
    _refused(root, "pkg/a.py", _at(text, "a\n"), capsys, ("pkg/a.py", 3), "b")


# --- check order ---------------------------------------------------------------------------------------------------

CAPTURED = "old = 1\n\n\ndef f() -> int:\n    fresh = 2\n    return old + fresh\n"


def test_names_are_checked_after_keep(typed_project: MakeProject) -> None:
    root = typed_project({"pkg/m.py": CAPTURED})
    assert _rename(root, "pkg/m.py", 0, NEW, "--keep", f"{root / 'pkg/m.py'}:6") == 0
    assert (root / "pkg/m.py").read_text(encoding="utf-8") == CAPTURED.replace("old = 1", "fresh = 1")


def test_a_name_conflict_is_reported_with_the_blindspot_refusal(
    typed_project: MakeProject, capsys: pytest.CaptureFixture[str]
) -> None:
    text = (
        "class C:\n    def old(self) -> int:\n        return 1\n\n    def fresh(self) -> int:\n        return 2\n\n\n"
        "def g(o) -> int:  # type: ignore[no-untyped-def]\n    return o.old()\n"
    )
    root = typed_project({"pkg/m.py": text})
    before = file_tree(root)
    assert _rename(root, "pkg/m.py", _at(text, "old")) == 1
    expected = [
        message("compliance.attr-blindspot", path="pkg/m.py", line=10, receiver="o", attr="old", type="Unknown"),
        message("refactor.name-conflict", name=NEW, path="pkg/m.py", line=5),
        message("refactor.blindspots", count=1, attr="old"),
    ]
    assert readouterr(capsys) == ("", "".join(f"{line}\n" for line in expected))
    assert file_tree(root) == before


# --- the implicit root's members -----------------------------------------------------------------------------------

def _object_members(stub: Path) -> set[str]:
    """Every member `object` declares in `stub`, under any version branch."""
    cls = next(n for n in ast.parse(stub.read_text(encoding="utf-8")).body
               if isinstance(n, ast.ClassDef) and n.name == "object")
    names: set[str] = set()

    def collect(body: list[ast.stmt]) -> None:
        for node in body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                names.add(node.name)
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                names.add(node.target.id)
            elif isinstance(node, ast.Assign):
                names.update(t.id for t in node.targets if isinstance(t, ast.Name))
            elif isinstance(node, ast.If):
                collect(node.body)
                collect(node.orelse)

    collect(cls.body)
    return names


def test_root_members_are_object_in_the_shipped_typeshed() -> None:
    spec = importlib.util.find_spec("basedpyright")
    assert spec is not None
    assert spec.origin is not None
    stub = Path(spec.origin).parent / "dist" / "typeshed-fallback" / "stdlib" / "builtins.pyi"
    assert language("python")["root_members"] == sorted(_object_members(stub))
