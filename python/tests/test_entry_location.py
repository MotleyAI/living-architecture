"""A Python rename's entry located without rope: the declaration at the locator's site, its kind and its canonical
key, and the entries merged when they locate the same symbol."""

from __future__ import annotations

from pathlib import Path

import pytest
from entry_source import ALT, OTHER, M, at, line
from project_files import write_project

from living_architecture.contract import message
from living_architecture.refactor.entry_location import EntryLocator
from living_architecture.refactor.locators import Locator, RefactorError

# (id, locator, kind, (rel, line of the group's first declaration, name))
TABLE = [
    ("def", Locator(offset=at("def top", inner="top")), "name", ("pkg/m.py", line("def top"), "top")),
    ("class", Locator(offset=at("class Box", inner="Box")), "name", ("pkg/m.py", line("class Box"), "Box")),
    ("positional-only", Locator(offset=at("(a, /", inner="a")), "parameter", ("pkg/m.py", line("def top"), "a")),
    ("positional", Locator(offset=at("/, b", inner="b")), "parameter", ("pkg/m.py", line("def top"), "b")),
    ("star-args", Locator(offset=at("*args", inner="args")), "parameter", ("pkg/m.py", line("def top"), "args")),
    ("keyword-only", Locator(offset=at(", c,", inner="c")), "parameter", ("pkg/m.py", line("def top"), "c")),
    ("kwargs", Locator(offset=at("**kwargs", inner="kwargs")), "parameter", ("pkg/m.py", line("def top"), "kwargs")),
    ("lambda", Locator(offset=at("lambda lam_arg", inner="lam_arg")), "parameter",
     ("pkg/m.py", line("lambda lam_arg"), "lam_arg")),
    ("assignment", Locator(offset=at("local = a")), "local", ("pkg/m.py", line("local = a"), "local")),
    ("augmented", Locator(offset=at("local += 1")), "local", ("pkg/m.py", line("local = a"), "local")),
    ("annotated", Locator(offset=at("ann: int")), "local", ("pkg/m.py", line("ann: int"), "ann")),
    ("walrus", Locator(offset=at("(walrus", inner="walrus")), "local", ("pkg/m.py", line("(walrus"), "walrus")),
    ("for", Locator(offset=at("for loop_var", inner="loop_var")), "local",
     ("pkg/m.py", line("for loop_var"), "loop_var")),
    ("with", Locator(offset=at("as handle", inner="handle")), "local", ("pkg/m.py", line("as handle"), "handle")),
    ("except", Locator(offset=at("as err", inner="err")), "local", ("pkg/m.py", line("as err"), "err")),
    ("match", Locator(offset=at("[matched]", inner="matched")), "local", ("pkg/m.py", line("[matched]"), "matched")),
    ("comprehension", Locator(offset=at("for comp_var", inner="comp_var")), "local",
     ("pkg/m.py", line("for comp_var"), "comp_var")),
    ("global", Locator(offset=at("global COUNTER", inner="COUNTER")), "name",
     ("pkg/m.py", line("COUNTER = 0"), "COUNTER")),
    ("nonlocal", Locator(offset=at("nonlocal shared", inner="shared")), "local",
     ("pkg/m.py", line("shared = 1"), "shared")),
    ("import-binding", Locator(symbol="thing"), "name", ("pkg/other.py", 1, "thing")),
    ("class-body-member", Locator(symbol="Box.size"), "member", ("pkg/m.py", line("size: int"), "size")),
    ("self-attribute", Locator(offset=at("self.weight", inner="weight")), "member",
     ("pkg/m.py", line("self.weight"), "weight")),
    ("method", Locator(symbol="Box.__init__"), "method", ("pkg/m.py", line("def __init__"), "__init__")),
    ("property-setter", Locator(offset=at("def label", 1, inner="label")), "method",
     ("pkg/m.py", line("def label"), "label")),
    ("overload", Locator(offset=at("def get", 1, inner="get")), "method", ("pkg/m.py", line("def get"), "get")),
    ("conditional-assignment", Locator(offset=at("MODE = 2")), "name", ("pkg/m.py", line("MODE = 1"), "MODE")),
    ("static-reference", Locator(offset=at("top(1", inner="top")), "name", ("pkg/m.py", line("def top"), "top")),
    ("reference-to-import", Locator(offset=at(", thing,", inner="thing")), "name", ("pkg/other.py", 1, "thing")),
    ("module-attribute", Locator(offset=at("other.thing", inner="thing")), "name", ("pkg/other.py", 1, "thing")),
]


class Definitions:
    """A stand-in for the language server's `definition`: the answers it gives, and the sites it was asked about."""

    def __init__(self, answers: dict[tuple[str, int], list[tuple[Path, int]]]) -> None:
        self.answers = answers
        self.asked: list[tuple[str, int]] = []

    def __call__(self, rel: str, offset: int) -> list[tuple[Path, int]]:
        self.asked.append((rel, offset))
        return self.answers.get((rel, offset), [])


@pytest.fixture
def root(tmp_path: Path) -> Path:
    return write_project(tmp_path / "proj", {"pkg/m.py": M, "pkg/other.py": OTHER, "pkg/alt.py": ALT})


@pytest.mark.parametrize(("locator", "kind", "declared"), [row[1:] for row in TABLE], ids=[row[0] for row in TABLE])
def test_a_locator_names_its_declarations_group(
    root: Path, locator: Locator, kind: str, declared: tuple[str, int, str]
) -> None:
    definitions = Definitions({})
    found = EntryLocator(root, definitions).locate("pkg/m.py", locator)
    assert (found.kind, found.key) == (kind, (kind, *declared))
    assert definitions.asked == []


def test_a_reference_only_the_checker_resolves_asks_its_definition(root: Path) -> None:
    site = at("b.size", inner="size")
    definitions = Definitions({("pkg/m.py", site): [(root / "pkg" / "m.py", at("size: int"))]})
    found = EntryLocator(root, definitions).locate("pkg/m.py", Locator(offset=site))
    assert (found.kind, found.key) == ("member", ("member", "pkg/m.py", line("size: int"), "size"))
    assert definitions.asked == [("pkg/m.py", site)]


def test_a_library_name_keys_by_the_entrys_site(root: Path, tmp_path: Path) -> None:
    site = at("len(", inner="len")
    builtins = tmp_path / "typeshed" / "builtins.pyi"
    definitions = Definitions({("pkg/m.py", site): [(builtins, 0)]})
    found = EntryLocator(root, definitions).locate("pkg/m.py", Locator(offset=site))
    assert found.key == ("site", "pkg/m.py", site, None)


def test_an_imported_module_is_a_module(root: Path) -> None:
    assert EntryLocator(root, Definitions({})).locate("pkg/m.py", Locator(symbol="other")).kind == "module"


@pytest.mark.parametrize("locator", [Locator(offset=at("\n\n\ndef top") + 1), Locator(offset=at("local += 1", inner="+="))],
                         ids=["whitespace", "operator"])
def test_a_location_that_is_not_an_identifier_cannot_be_renamed(root: Path, locator: Locator) -> None:
    with pytest.raises(RefactorError, match=message("refactor.cannot-rename")):
        EntryLocator(root, Definitions({})).locate("pkg/m.py", locator)


def test_a_reference_that_resolves_to_nothing_cannot_be_renamed(root: Path) -> None:
    with pytest.raises(RefactorError, match=message("refactor.cannot-rename")):
        EntryLocator(root, Definitions({})).locate("pkg/m.py", Locator(offset=at("nowhere")))


def test_a_reference_that_resolves_to_two_groups_cannot_be_renamed(root: Path) -> None:
    site = at(", either,", inner="either")
    both = [(root / "pkg" / "other.py", 0), (root / "pkg" / "alt.py", 0)]
    with pytest.raises(RefactorError, match=message("refactor.cannot-rename")):
        EntryLocator(root, Definitions({("pkg/m.py", site): both})).locate("pkg/m.py", Locator(offset=site))


@pytest.mark.parametrize("locator", [Locator(symbol="foo"), Locator(offset=4)], ids=["symbol", "offset"])
def test_an_entry_in_a_file_with_a_byte_order_mark(root: Path, locator: Locator) -> None:
    (root / "pkg" / "bom.py").write_bytes(b"\xef\xbb\xbfdef foo() -> int:\n    return 1\n")
    found = EntryLocator(root, Definitions({})).locate("pkg/bom.py", locator)
    assert found.key == ("name", "pkg/bom.py", 1, "foo")
