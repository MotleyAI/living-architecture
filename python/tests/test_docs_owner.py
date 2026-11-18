"""Python `rename --docs`: a code-marked bare mention is decided by its owning class, once over all entries."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from refactor_cli import git_project, leftover, read, rename_argv, run

from living_architecture.contract import message

Run = tuple[int, str, str]


@pytest.fixture
def docs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]):
    """Run `A.field -> column --docs` (or `argv`) over `files`; returns the project root and the run."""

    def go(files: dict[str, str], *flags: str, argv: list[str] | None = None) -> tuple[Path, Run]:
        root = git_project(tmp_path / "proj", files)
        return root, run(root, argv or rename_argv("pkg/a.py", "A.field", "column", "--docs", *flags), monkeypatch, capsys)

    return go


A = 'class A:\n    """Carries ``field``."""\n\n    field: str = ""\n'
A_AFTER = 'class A:\n    """Carries ``column``."""\n\n    column: str = ""\n'


def _line(text: str, needle: str) -> int:
    return text[: text.index(needle)].count("\n") + 1


def test_another_class_declaring_the_member_keeps_its_docstring(docs) -> None:
    other = '\n\nclass B:\n    """Carries ``field``; another class."""\n\n    field: str = ""\n'
    root, (code, _out, err) = docs({"pkg/a.py": A + other}, "--without", "pkg/a.py:10")
    assert code == 0
    assert read(root, "pkg/a.py") == A_AFTER + other
    assert err == f"{leftover('pkg/a.py', 8, 'docstring', 'field')}\n"


def test_a_decorated_class_owns_from_its_first_decorator(docs) -> None:
    head = "from typing import final\n\n\n"
    b = '@final  # keeps `field`\nclass B:\n    field: str = ""\n'
    a = "@final  # keeps `field`\n" + A
    root, (code, _out, err) = docs({"pkg/a.py": head + b + "\n\n" + a}, "--without", "pkg/a.py:6")
    assert code == 0
    assert read(root, "pkg/a.py") == head + b + "\n\n" + "@final  # keeps `column`\n" + A_AFTER
    assert err == f"{leftover('pkg/a.py', 4, 'comment', 'field')}\n"


def test_a_comment_above_a_class_is_not_owned_by_it(docs) -> None:
    text = "# `field` of A\n" + A + '\n\n# `field` of B\nclass B:\n    field: str = ""\n'
    root, (code, _out, err) = docs({"pkg/a.py": text}, "--without", "pkg/a.py:10")
    assert code == 0
    assert read(root, "pkg/a.py") == text.replace(A, A_AFTER)
    assert err.splitlines() == [leftover("pkg/a.py", 1, "comment", "field"), leftover("pkg/a.py", 8, "comment", "field")]


def test_a_nested_class_without_the_member_leaves_the_mention_to_the_enclosing_class(docs) -> None:
    nested = '\n    class Meta:\n        """Options of ``field``."""\n'
    root, (code, _out, err) = docs({"pkg/a.py": A + nested})
    assert (code, err) == (0, "")
    assert read(root, "pkg/a.py") == A_AFTER + nested.replace("field", "column")


def test_a_nested_class_declaring_the_member_owns_its_mention(docs) -> None:
    nested = '\n    class Meta:\n        """Options of ``field``."""\n\n        field: int = 0\n'
    root, (code, _out, err) = docs({"pkg/a.py": A + nested}, "--without", "pkg/a.py:9")
    assert code == 0
    assert read(root, "pkg/a.py") == A_AFTER + nested
    assert err == f"{leftover('pkg/a.py', 7, 'docstring', 'field')}\n"


def test_a_class_without_the_member_falls_back_to_the_file(docs) -> None:
    helper = '\n\nclass Helper:\n    """Formats ``field`` values."""\n'
    root, (code, _out, err) = docs({"pkg/a.py": A + helper})
    assert (code, err) == (0, "")
    assert read(root, "pkg/a.py") == A_AFTER + helper.replace("field", "column")


def test_a_subclass_inheriting_the_member_owns_its_mention(docs) -> None:
    sub = '\n\nclass Sub(A):\n    """Reads ``field``."""\n'
    root, (code, _out, err) = docs({"pkg/a.py": A + sub})
    assert (code, err) == (0, "")
    assert read(root, "pkg/a.py") == A_AFTER + sub.replace("field", "column")


def test_a_lookup_landing_on_an_unchanged_declaration_is_listed(docs) -> None:
    rest = '\n\nclass Other:\n    field: str = ""\n\n\nclass Mixed(Other, A):\n    """Reads ``field``."""\n'
    root, (code, _out, err) = docs({"pkg/a.py": A + rest}, "--without", "pkg/a.py:8")
    assert code == 0
    assert read(root, "pkg/a.py") == A_AFTER + rest
    assert err == f"{leftover('pkg/a.py', 12, 'docstring', 'field')}\n"


def test_an_unresolved_base_before_the_member_is_listed(docs) -> None:
    rest = '\n\nclass C(Unknown, A):  # type: ignore[name-defined]\n    """Reads ``field``."""\n'
    root, (code, _out, err) = docs({"pkg/a.py": A + rest})
    assert code == 0
    assert read(root, "pkg/a.py") == A_AFTER + rest
    assert leftover("pkg/a.py", 8, "docstring", "field") in err.splitlines()


def test_an_unresolved_base_after_the_member_is_found_does_not_matter(docs) -> None:
    rest = '\n\nclass C(A, Unknown):  # type: ignore[name-defined]\n    """Reads ``field``."""\n'
    root, (code, _out, _err) = docs({"pkg/a.py": A + rest})
    assert code == 0
    assert read(root, "pkg/a.py") == A_AFTER + rest.replace("``field``", "``column``")


MODULE = '"""Rows carry ``field``."""\n# see `field()` and :attr:`field`\n\n\n'


def test_a_module_level_mention_follows_the_only_declaration(docs) -> None:
    show = '\n\ndef show(a: A) -> str:\n    """Returns ``field``."""\n    return a.field\n'
    root, (code, _out, err) = docs({"pkg/a.py": MODULE + A + show})
    assert (code, err) == (0, "")
    assert read(root, "pkg/a.py") == (MODULE + A + show).replace("field", "column")


@pytest.mark.parametrize(
    ("other", "flags"),
    [
        ('\n\nclass B:\n    field: str = ""\n', ("--without", "pkg/a.py:12")),
        ("\n\nfield = 1\n", ()),
        ("\n\ndef field() -> int:\n    return 1\n", ()),
    ],
    ids=["class-member", "module-variable", "module-function"],
)
def test_a_module_level_mention_beside_an_unchanged_declaration_is_listed(docs, other: str, flags: tuple[str, ...]) -> None:
    root, (code, _out, err) = docs({"pkg/a.py": MODULE + A + other}, *flags)
    assert code == 0
    assert read(root, "pkg/a.py") == MODULE + A_AFTER + other
    assert err.splitlines() == [
        leftover("pkg/a.py", 1, "docstring", "field"),
        leftover("pkg/a.py", 2, "comment", "field"),
        leftover("pkg/a.py", 2, "comment", "field"),
    ]


def test_a_stand_in_renamed_with_the_member_keeps_the_file_rule(docs) -> None:
    other = '\n\nclass B:\n    """Carries ``field`` too."""\n\n    field: str = ""\n'
    root, (code, _out, err) = docs({"pkg/a.py": MODULE + A + other}, "--with", "pkg/a.py:14")
    assert (code, err) == (0, "")
    assert read(root, "pkg/a.py") == (MODULE + A + other).replace("field", "column")


def test_a_plain_module_level_word_is_listed(docs) -> None:
    text = "# field is plain here\n" + A
    root, (code, _out, err) = docs({"pkg/a.py": text})
    assert code == 0
    assert read(root, "pkg/a.py") == "# field is plain here\n" + A_AFTER
    assert err == f"{leftover('pkg/a.py', 1, 'comment', 'field')}\n"


@pytest.mark.parametrize("message_text", ['"field: missing"', '"field (unset)"', '"field of a row"', 'f"field: {x}"'])
def test_a_plain_word_opening_a_string_is_listed(docs, message_text: str) -> None:
    method = f"\n    def check(self, x: int) -> str:\n        return {message_text}\n"
    root, (code, _out, err) = docs({"pkg/a.py": A + method})
    assert code == 0
    assert read(root, "pkg/a.py") == A_AFTER + method
    assert err == f"{leftover('pkg/a.py', 7, 'string', 'field')}\n"


def test_a_code_marked_mention_in_another_file_is_listed(docs) -> None:
    use = 'from pkg.a import A\n\n\nclass View(A):\n    """Shows ``field``."""\n'
    root, (code, _out, err) = docs({"pkg/a.py": A, "pkg/use.py": use})
    assert code == 0
    assert read(root, "pkg/use.py") == use
    assert err == f"{leftover('pkg/use.py', 5, 'docstring', 'field')}\n"


TABLES = (
    '"""Every table lists its ``columns``."""\n\n\n'
    'class Table:\n    """A table and its ``columns``."""\n\n    columns: list[str] = []\n\n\n'
    'class Result:\n    """A result and its ``columns``."""\n\n    columns: list[str] = []\n'
)
TWO_ENTRIES = [
    {"file": "pkg/a.py", "symbol": "Table.columns", "new_name": "fields"},
    {"file": "pkg/a.py", "symbol": "Result.columns", "new_name": "result_columns"},
]


def test_two_entries_sharing_an_old_name_resolve_each_mention_once(docs) -> None:
    files = {"pkg/a.py": TABLES, "map.yaml": yaml.safe_dump(TWO_ENTRIES, sort_keys=False)}
    root, (code, _out, err) = docs(files, argv=["--apply", "rename-map", "map.yaml", "--docs"])
    assert code == 0
    after = read(root, "pkg/a.py").splitlines()
    assert [after[0], after[4], after[6], after[10], after[12]] == [
        '"""Every table lists its ``columns``."""',
        '    """A table and its ``fields``."""',
        "    fields: list[str] = []",
        '    """A result and its ``result_columns``."""',
        "    result_columns: list[str] = []",
    ]
    assert err == f"{leftover('pkg/a.py', 1, 'docstring', 'columns')}\n"


def test_a_lookup_through_two_renamed_bases_takes_the_first_in_the_mro(docs) -> None:
    both = '\n\nclass Both(Table, Result):\n    """Reads ``columns``."""\n'
    files = {"pkg/a.py": TABLES + both, "map.yaml": yaml.safe_dump(TWO_ENTRIES, sort_keys=False)}
    root, (code, _out, err) = docs(files, argv=["--apply", "rename-map", "map.yaml", "--docs"])
    assert code == 0
    assert read(root, "pkg/a.py").splitlines()[16] == '    """Reads ``fields``."""'
    assert err == f"{leftover('pkg/a.py', 1, 'docstring', 'columns')}\n"


def test_two_entries_never_refuse_a_docs_mention_as_a_map_conflict(docs) -> None:
    files = {"pkg/a.py": TABLES, "map.yaml": yaml.safe_dump(TWO_ENTRIES, sort_keys=False)}
    _root, (code, _out, err) = docs(files, argv=["rename-map", "map.yaml", "--docs"])
    conflict = message("refactor.map-conflict", path="pkg/a.py", line=1, first=1, second=2)
    assert (code, conflict in err) == (0, False)


def test_two_entries_converging_on_one_name_rewrite_the_module_mention(docs) -> None:
    entries = [{**TWO_ENTRIES[0]}, {**TWO_ENTRIES[1], "new_name": "fields"}]
    files = {"pkg/a.py": TABLES, "map.yaml": yaml.safe_dump(entries, sort_keys=False)}
    root, (code, _out, err) = docs(files, argv=["--apply", "rename-map", "map.yaml", "--docs"])
    assert (code, err) == (0, "")
    assert read(root, "pkg/a.py") == TABLES.replace("columns", "fields")
