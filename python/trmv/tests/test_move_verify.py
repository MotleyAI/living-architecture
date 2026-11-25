"""A Python move resolves the project as it would leave it and refuses when a name would resolve differently."""

from __future__ import annotations

import os
import tempfile
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import NamedTuple

import pytest

from project_files import file_tree, write_project
from refactor_cli import run
from trmv.contract import message
from trmv.refactor import rope_refactor
from trmv.refactor.module_move import ModuleMove
from trmv.refactor.move_project import MoveProject
from trmv.refactor.move_verify import Fingerprint, Moved, fingerprint
from trmv.refactor.moved_symbol import MovedSymbol

Texts = dict[str, str]
Fault = Callable[[Texts], Texts]

F = "def f():\n    return 1\n"
B = '"""B."""\n'
MOVE_F = ["move-symbol", "--file", "pkg/a.py", "--symbol", "f", "--dest", "pkg/b.py"]
FLAGS = pytest.mark.parametrize("flags", [[], ["--apply"]], ids=["dry-run", "apply"])


class Case(NamedTuple):
    """A move over `files`, the `fault` injected into the planner's texts, and the difference it must be refused for."""

    files: Texts
    argv: list[str]
    fault: Fault
    path: str
    line: int
    name: str


def _without_line(rel: str, line: str) -> Fault:
    def fault(texts: Texts) -> Texts:
        assert line in texts[rel]
        return {**texts, rel: texts[rel].replace(line, "", 1)}

    return fault


def _with_text(rel: str, text: str) -> Fault:
    return lambda texts: {**texts, rel: text}


def _dropped(rel: str) -> Fault:
    def fault(texts: Texts) -> Texts:
        assert rel in texts
        return {k: v for k, v in texts.items() if k != rel}

    return fault


def _both(first: Fault, second: Fault) -> Fault:
    return lambda texts: second(first(texts))


USE_OS = "import os\n\n\nprint(os.sep)\n"
CASES = {
    "read-without-its-binding": Case(
        {"pkg/a.py": "import os\n\n\ndef f():\n    return os.sep\n", "pkg/b.py": B},
        MOVE_F, _without_line("pkg/b.py", "import os\n"), "pkg/b.py", 5, "os.sep"),
    "use-before-the-moved-declaration": Case(
        {"pkg/a.py": F, "pkg/b.py": "from pkg.a import f\nX = f()\n"},
        MOVE_F, _with_text("pkg/b.py", "X = f()\n\n\n" + F), "pkg/b.py", 1, "f"),
    "re-export": Case(
        {"pkg/__init__.py": "from pkg.a import f\n", "pkg/a.py": F, "pkg/b.py": B, "pkg/c.py": F},
        MOVE_F, _with_text("pkg/__init__.py", "from pkg.c import f\n"), "pkg/__init__.py", 1, "f"),
    "missed-importer": Case(
        {"pkg/a.py": F, "pkg/b.py": B, "pkg/use.py": "from pkg.a import f\nf()\n"},
        MOVE_F, _dropped("pkg/use.py"), "pkg/use.py", 2, "f"),
    "move-module-missed-importer": Case(
        {"pkg/a.py": F, "dst/__init__.py": "", "use.py": "import pkg.a\npkg.a.f()\n"},
        ["move-module", "--module", "pkg/a.py", "--dest", "dst"], _dropped("use.py"), "use.py", 2, "pkg.a.f"),
    "export-list": Case(
        {"pkg/a.py": '__all__ = ["f"]\n\n\n' + F, "pkg/b.py": B},
        MOVE_F, _with_text("pkg/a.py", '__all__ = ["f"]\n'), "pkg/a.py", 1, "__all__"),
    "missing-read-at-its-old-line": Case(
        {"pkg/a.py": F, "pkg/b.py": B, "pkg/use.py": USE_OS},
        MOVE_F, _with_text("pkg/use.py", "import os\n"), "pkg/use.py", 4, "print"),
    "added-read-before-a-missing-one": Case(
        {"pkg/a.py": F, "pkg/b.py": B, "pkg/use.py": USE_OS},
        MOVE_F, _with_text("pkg/use.py", "import os\nzzz\n"), "pkg/use.py", 2, "zzz"),
    "earlier-file-first": Case(
        {"pkg/a.py": '__all__ = ["f"]\n\n\n' + F, "pkg/b.py": B, "pkg/use.py": "from pkg.a import f\nf()\n"},
        MOVE_F, _both(_with_text("pkg/a.py", '__all__ = ["f"]\n'), _dropped("pkg/use.py")), "pkg/a.py", 1, "__all__"),
}
CASE = pytest.mark.parametrize("case", list(CASES.values()), ids=list(CASES))


def _inject(monkeypatch: pytest.MonkeyPatch, fault: Fault) -> None:
    """Pass the texts both planners return through `fault`."""
    symbol_texts: Callable[[MoveProject, str, MovedSymbol, str], Texts] = rope_refactor.symbol_move_texts
    module_texts: Callable[[MoveProject, str, str], tuple[ModuleMove, Texts]] = rope_refactor.module_move_texts

    def symbol(project: MoveProject, source: str, moved: MovedSymbol, dest: str) -> Texts:
        return fault(symbol_texts(project, source, moved, dest))

    def module(project: MoveProject, source: str, dest: str) -> tuple[ModuleMove, Texts]:
        move, texts = module_texts(project, source, dest)
        return move, fault(texts)

    monkeypatch.setattr(rope_refactor, "symbol_move_texts", symbol)
    monkeypatch.setattr(rope_refactor, "module_move_texts", module)


def _listing(root: Path) -> list[str]:
    """Every file and directory under `root`."""
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*"))


@CASE
@FLAGS
def test_a_planner_fault_is_refused_naming_the_first_difference(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], case: Case, flags: list[str]
) -> None:
    root = write_project(tmp_path / "proj", case.files)
    before = file_tree(root)
    _inject(monkeypatch, case.fault)
    finding = message("refactor.resolution-changed", path=case.path, line=case.line, name=case.name)
    assert run(root, [*flags, *case.argv], monkeypatch, capsys) == (1, "", finding + "\n")
    assert file_tree(root) == before


@CASE
def test_the_same_move_without_the_fault_is_not_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], case: Case
) -> None:
    root = write_project(tmp_path / "proj", case.files)
    code, _out, err = run(root, ["--apply", *case.argv], monkeypatch, capsys)
    assert (code, err) == (0, "")


def test_a_symlink_to_a_project_file_is_not_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = write_project(tmp_path / "proj", {"pkg/a.py": F, "pkg/b.py": B, "pkg/c.py": "from pkg.a import f\nf()\n"})
    try:
        os.symlink("pkg/c.py", root / "link.py")
    except (OSError, NotImplementedError):
        pytest.skip("no symlinks on this platform")
    code, _out, err = run(root, MOVE_F, monkeypatch, capsys)
    assert (code, err) == (0, "")


def test_a_dry_run_creates_nothing_under_the_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = write_project(tmp_path / "proj", {"pkg/a.py": F, "pkg/b.py": B})
    before = _listing(root)
    assert run(root, MOVE_F, monkeypatch, capsys)[0] == 0
    assert _listing(root) == before


def test_a_refused_apply_creates_nothing_under_the_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    case = CASES["read-without-its-binding"]
    root = write_project(tmp_path / "proj", case.files)
    before = _listing(root)
    _inject(monkeypatch, case.fault)
    assert run(root, ["--apply", *case.argv], monkeypatch, capsys)[0] == 1
    assert _listing(root) == before


@pytest.mark.usefixtures("no_server")
@pytest.mark.parametrize(("fault", "code"), [(None, 0), (CASES["read-without-its-binding"].fault, 1)],
                         ids=["accepted", "refused"])
def test_the_comparison_starts_no_language_server(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], fault: Fault | None, code: int
) -> None:
    root = write_project(tmp_path / "proj", CASES["read-without-its-binding"].files)
    if fault is not None:
        _inject(monkeypatch, fault)
    assert run(root, MOVE_F, monkeypatch, capsys)[0] == code


@pytest.fixture
def verify_dirs(monkeypatch: pytest.MonkeyPatch) -> list[Path]:
    """Every temporary directory the comparison makes."""
    made: list[Path] = []
    real = tempfile.TemporaryDirectory

    def recording(*, prefix: str) -> tempfile.TemporaryDirectory[str]:
        directory = real(prefix=prefix)
        made.append(Path(directory.name))
        return directory

    monkeypatch.setattr("trmv.refactor.move_verify.tempfile.TemporaryDirectory", recording)
    return made


@FLAGS
@pytest.mark.parametrize(("fault", "code"), [(None, 0), (CASES["read-without-its-binding"].fault, 1)],
                         ids=["accepted", "refused"])
def test_the_comparison_removes_its_temporary_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], verify_dirs: list[Path],
    fault: Fault | None, code: int, flags: list[str],
) -> None:
    root = write_project(tmp_path / "proj", CASES["read-without-its-binding"].files)
    if fault is not None:
        _inject(monkeypatch, fault)
    assert run(root, [*flags, *MOVE_F], monkeypatch, capsys)[0] == code
    assert [d.name.startswith("la-verify-") for d in verify_dirs] == [True]
    assert not verify_dirs[0].exists()
    assert not verify_dirs[0].is_relative_to(root)


# ---- the fingerprint

DECL_F = ("decl", "pkg/a.py", "f", 0)


def _print(tmp_path: Path, files: Texts, rel: str = "use.py", name: str = "proj") -> Fingerprint:
    return fingerprint(MoveProject(write_project(tmp_path / name, files)), rel)


def _read_at(found: Fingerprint, line: int, text: str) -> tuple[object, str, str]:
    """The key of the read written `text` on `line`."""
    keys = [key for key, sites in found.sites.items() if any((at, src) == (line, text) for at, _col, src in sites)]
    assert len(keys) == 1, keys
    return keys[0]


def test_a_maximal_chain_is_one_read(tmp_path: Path) -> None:
    found = _print(tmp_path, {"pkg/a.py": F, "use.py": "import pkg.a\n\nx = pkg.a.f.attr\n"})
    assert found.reads == Counter({(DECL_F, "attr", "bound"): 1})
    assert [(line, text) for line, _col, text in found.sites[(DECL_F, "attr", "bound")]] == [(3, "pkg.a.f.attr")]


def test_a_chain_on_a_call_is_no_read(tmp_path: Path) -> None:
    found = _print(tmp_path, {"use.py": "x = str().upper\n"})
    assert found.reads == Counter({(("unbound", "str"), "", "not-yet"): 1})


def test_a_builtin_is_unbound_and_a_parameter_opaque(tmp_path: Path) -> None:
    found = _print(tmp_path, {"use.py": "def g(p):\n    return len(p)\n"})
    assert found.reads == Counter({(("unbound", "len"), "", "deferred"): 1, (("opaque", "p"), "", "deferred"): 1})


def test_the_tail_follows_the_longest_resolved_prefix(tmp_path: Path) -> None:
    found = _print(tmp_path, {"use.py": "import os\n\nx = os.path.sep\n"})
    assert found.reads == Counter({(("module", "os"), "path.sep", "bound"): 1})


ORDERS = """import os

a = os.sep
b = later
later = 1


def g(q: os.PathLike) -> str:
    return os.sep


class C:
    x = 1
    y = x
"""


@pytest.mark.parametrize(
    ("line", "text", "key"),
    [
        (3, "os.sep", (("module", "os"), "sep", "bound")),
        (4, "later", (("decl", "use.py", "later", 0), "", "not-yet")),
        (8, "os.PathLike", (("module", "os"), "PathLike", "annotation")),
        (8, "str", (("unbound", "str"), "", "annotation")),
        (9, "os.sep", (("module", "os"), "sep", "deferred")),
        (14, "x", (("local", "x"), "", "local")),
    ],
    ids=["bound", "not-yet", "annotation", "annotation-unbound", "deferred", "local"],
)
def test_a_read_carries_its_order(tmp_path: Path, line: int, text: str, key: tuple[object, str, str]) -> None:
    found = _print(tmp_path, {"use.py": ORDERS})
    assert _read_at(found, line, text) == key
    assert sum(found.reads.values()) == 6


def test_a_star_import_before_a_read_binds_every_name(tmp_path: Path) -> None:
    found = _print(tmp_path, {"pkg/a.py": F, "use.py": "g()\nfrom pkg.a import *\nf()\nh()\n"})
    assert found.reads == Counter({(("unbound", "g"), "", "not-yet"): 1, (DECL_F, "", "bound"): 1,
                                   (("unbound", "h"), "", "bound"): 1})


def test_a_nested_declaration_is_local(tmp_path: Path) -> None:
    found = _print(tmp_path, {"use.py": "def outer():\n    def inner():\n        return 1\n    return inner\n"})
    assert found.reads == Counter({(("local", "inner"), "", "deferred"): 1})


def test_a_read_of_type_checking_is_left_out(tmp_path: Path) -> None:
    found = _print(tmp_path, {"use.py": "from typing import TYPE_CHECKING\n\nif TYPE_CHECKING:\n    import os\n"})
    assert found.reads == Counter()
    assert found.names == {"TYPE_CHECKING": ("typing", "TYPE_CHECKING"), "os": ("module", "os")}


def test_top_level_names_carry_their_canonical_values(tmp_path: Path) -> None:
    files = {"pkg/a.py": F, "use.py": "import pkg.a as m\nfrom pkg.a import f\n\n\ndef g(p):\n    return p\n\n\nx = g(1)\n"}
    assert _print(tmp_path, files).names == {
        "m": ("module", "pkg/a.py"), "f": DECL_F, "g": ("decl", "use.py", "g", 0), "x": ("decl", "use.py", "x", 0)}


def test_a_name_bound_to_two_values_is_unknown(tmp_path: Path) -> None:
    found = _print(tmp_path, {"use.py": "import os as m\nimport sys as m\n"})
    assert found.names == {"m": "?"}


def test_exports_are_the_literal_all(tmp_path: Path) -> None:
    files = {"pkg/a.py": '__all__ = ["f", "g"]\n' + F, "use.py": "x = 1\n"}
    assert _print(tmp_path, files, "pkg/a.py").exports == {"f", "g"}
    assert _print(tmp_path, files).exports is None


USE_F = "from pkg.a import f\nimport pkg.a as m\n\nprint(f(), m.f)\n"


def test_a_declaration_keeps_its_value_when_lines_shift(tmp_path: Path) -> None:
    here = _print(tmp_path, {"pkg/a.py": F, "use.py": USE_F})
    shifted = _print(tmp_path, {"pkg/a.py": "\n\n\n" + F, "use.py": USE_F}, name="shifted")
    assert (shifted.reads, shifted.names) == (here.reads, here.names)
    assert here.names == {"f": DECL_F, "m": ("module", "pkg/a.py")}


def test_a_declaration_keeps_its_value_when_its_file_moves(tmp_path: Path) -> None:
    before = MoveProject(write_project(tmp_path / "before", {"pkg/a.py": F, "use.py": USE_F}))
    moved = USE_F.replace("pkg.a", "dst.a")
    after = _print(tmp_path, {"dst/__init__.py": "", "dst/a.py": F, "use.py": moved}, name="after")
    found = fingerprint(before, "use.py", final=lambda rel: "dst/a.py" if rel == "pkg/a.py" else rel)
    assert (found.reads, found.names) == (after.reads, after.names)
    assert found.names == {"f": ("decl", "dst/a.py", "f", 0), "m": ("module", "dst/a.py")}


TWO_F = "def f(n=0):\n    return n\n\n\ndef f():\n    return 1\n"


def test_bindings_that_agree_once_canonical_are_one_value(tmp_path: Path) -> None:
    files = {"pkg/a.py": F, "use.py": "import pkg.a as m\nimport pkg.a as m\nfrom pkg.a import f\nfrom pkg.a import f\n\nf\n"}
    found = _print(tmp_path, files)
    assert found.names == {"m": ("module", "pkg/a.py"), "f": DECL_F}
    assert found.reads == Counter({(DECL_F, "", "bound"): 1})


def test_two_declarations_of_a_name_are_unknown_unless_both_move(tmp_path: Path) -> None:
    project = MoveProject(write_project(tmp_path / "proj", {"pkg/a.py": TWO_F, "use.py": "import pkg.a\n\npkg.a.f\n"}))
    assert fingerprint(project, "use.py").reads == Counter({(("module", "pkg/a.py"), "f", "bound"): 1})
    module = project.module("pkg/a.py")
    assert module is not None
    moved = Moved(file="pkg/a.py", keys=frozenset(module.binder.decls), name="f", dest="pkg/b.py")
    assert fingerprint(project, "use.py", moved=moved).reads == Counter({(("decl", "pkg/b.py", "f", "moved"), "", "bound"): 1})


def test_a_chain_stops_at_a_package_that_answers_attributes_itself(tmp_path: Path) -> None:
    files = {"pkg/sql/__init__.py": "def __getattr__(name):\n    raise AttributeError(name)\n", "pkg/sql/client.py": "X = 1\n",
             "pkg/plain/__init__.py": "", "pkg/plain/client.py": "X = 1\n",
             "use.py": "import pkg.sql as s\nimport pkg.plain as p\n\nprint(s.client.X, p.client.X)\n"}
    found = _print(tmp_path, files)
    assert _read_at(found, 4, "s.client.X") == (("module", "pkg/sql/__init__.py"), "client.X", "bound")
    assert _read_at(found, 4, "p.client.X") == (("decl", "pkg/plain/client.py", "X", 0), "", "bound")


def test_a_read_that_becomes_bound_is_not_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    late = "def load():\n    global f\n    from pkg.a import f\n\n\nload()\nf()\n"
    root = write_project(tmp_path / "proj", {"pkg/a.py": F, "pkg/b.py": B, "pkg/use.py": late})
    _inject(monkeypatch, _with_text("pkg/use.py", "from pkg.b import f\n\n\ndef load():\n    pass\n\n\nload()\nf()\n"))
    code, _out, err = run(root, MOVE_F, monkeypatch, capsys)
    assert (code, err) == (0, "")


# ---- parsing each file once


def test_the_resolver_loads_the_projects_own_module(tmp_path: Path) -> None:
    project = MoveProject(write_project(tmp_path / "proj", {"pkg/a.py": F, "broken.py": "def f(:\n"}))
    assert project.resolver.load("pkg.a") is project.module("pkg/a.py")
    assert project.resolver.load("broken") is None


def test_an_adopted_module_is_the_files_model_at_its_own_root(tmp_path: Path) -> None:
    before = MoveProject(write_project(tmp_path / "before", {"pkg/a.py": F}))
    after = MoveProject(write_project(tmp_path / "after", {"pkg/a.py": F, "src/pkg/a.py": F, "src/pkg/__init__.py": ""}))
    module = before.module("pkg/a.py")
    assert module is not None
    after.adopt("pkg/a.py", module)
    after.adopt("src/pkg/a.py", module)
    adopted = after.module("pkg/a.py")
    assert adopted is not None
    assert (adopted.binder, adopted.path) == (module.binder, after.root / "pkg/a.py")
    assert after.resolver.load("pkg.a") is adopted
    other = after.module("src/pkg/a.py")
    assert other is not None
    assert other.binder is not module.binder
