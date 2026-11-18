"""The Python `Literal` probe asks the checker only about the files it can affect, and pulls a file's pre-probe
diagnostics only after a round shows that file an error."""

from __future__ import annotations

from pathlib import Path

import pytest
from project_files import file_tree, write_project
from refactor_cli import read, run

from living_architecture.contract import message
from living_architecture.lang import Diagnostic, Span
from living_architecture.lang.language_server import LanguageServer

KINDS = 'from typing import Literal\n\nDriftKind = Literal["edit_model", "drop"]\n'
USE = 'from pkg.kinds import DriftKind\n\n\ndef f(kind: DriftKind) -> None:\n    print(kind)\n\n\ndef call() -> None:\n    f("edit_model")\n'
REVEAL_ONLY = 'from pkg.kinds import DriftKind\n\n\ndef cmp(kind: DriftKind | str) -> bool:\n    return kind == "edit_model"\n'
AWAY = 'from pkg.use import f\n\nx: int = "nope"\n\n\ndef call() -> None:\n    f("edit_model")\n'
LOOSE = 'def n(o: int) -> None:\n    print(o)\n\n\ndef call() -> None:\n    n("edit_model")\n'
OUTSIDE = 's: str = "edit_model"\n'
LONELY = "def lonely() -> int:\n    return 1\n"
CLEAN = 'from pkg.kinds import DriftKind\n\nK: DriftKind = "drop"\n'
PROJECT = {
    "pkg/__init__.py": "",
    "pkg/kinds.py": KINDS,
    "pkg/use.py": USE,
    "pkg/cmp.py": REVEAL_ONLY,
    "pkg/away.py": AWAY,
    "pkg/loose.py": LOOSE,
    "pkg/strs.py": OUTSIDE,
    "pkg/lonely.py": LONELY,
    "pkg/clean.py": CLEAN,
}
RENAME = ["--apply", "rename", "--file", "pkg/kinds.py", "--symbol", "DriftKind['edit_model']", "--new-name", "edit_master"]


class Spy:
    """Records what the probe opens and pulls; a pull while every opened file holds its opened text is a `before` pull."""

    def __init__(self, root: Path, inject: dict[str, list[tuple[str, int, int]]] | None = None) -> None:
        self.root = root
        self.inject = inject or {}
        self.original: dict[Path, str] = {}
        self.current: dict[Path, str] = {}
        self.opened: list[str] = []
        self.pulled: list[str] = []
        self.before: list[str] = []
        self.rounds: list[list[str]] = []
        self.flagged: set[str] = set()
        self.unflagged_before: list[str] = []

    def rel(self, path: Path) -> str:
        return path.relative_to(self.root).as_posix()

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        opened, changed, pulled = LanguageServer.open, LanguageServer.change, LanguageServer.diagnostics

        def open_(server: LanguageServer, path: Path, text: str) -> None:
            self.original[path] = self.current[path] = text
            self.opened.append(self.rel(path))
            opened(server, path, text)

        def change(server: LanguageServer, path: Path, text: str) -> None:
            reverted = self._reverted()
            self.current[path] = text
            if reverted and not self._reverted():
                self.rounds.append([])
            changed(server, path, text)

        def diagnostics(server: LanguageServer, path: Path) -> list[Diagnostic]:
            found = [*pulled(server, path), *self._injected(path)]
            rel = self.rel(path)
            self.pulled.append(rel)
            if self._reverted():
                self.before.append(rel)
                if rel not in self.flagged:
                    self.unflagged_before.append(rel)
            else:
                self.rounds[-1].append(rel)
                if any(d.severity in (1, 2) for d in found):
                    self.flagged.add(rel)
            return found

        monkeypatch.setattr(LanguageServer, "open", open_)
        monkeypatch.setattr(LanguageServer, "change", change)
        monkeypatch.setattr(LanguageServer, "diagnostics", diagnostics)

    def _reverted(self) -> bool:
        return all(self.current[p] == self.original[p] for p in self.current)

    def _injected(self, path: Path) -> list[Diagnostic]:
        """A pre-existing error on each injected (code, start, end) of an unsubstituted file."""
        if self.current.get(path) != self.original.get(path):
            return []
        return [Diagnostic(span=Span(path=path, start=start, end=end), code=code, severity=1, message="pre-existing")
                for code, start, end in self.inject.get(self.rel(path), [])]


def _leftover(path: str, line: int) -> str:
    return message("refactor.leftover", path=path, line=line, where="string", old="edit_model")


def _probe(tmp_path: Path, files: dict[str, str], monkeypatch: pytest.MonkeyPatch,
           inject: dict[str, list[tuple[str, int, int]]] | None = None) -> tuple[Path, Spy]:
    root = write_project(tmp_path / "proj", files)
    spy = Spy(root, inject)
    spy.install(monkeypatch)
    return root, spy


def test_a_file_that_reaches_nothing_and_holds_no_equal_string_is_never_opened_nor_pulled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root, spy = _probe(tmp_path, PROJECT, monkeypatch)
    code, _out, err = run(root, RENAME, monkeypatch, capsys)
    assert (code, err.splitlines()) == (0, [_leftover("pkg/loose.py", 6), _leftover("pkg/strs.py", 1)])
    assert "pkg/lonely.py" not in spy.opened
    assert "pkg/lonely.py" not in spy.pulled
    for rel in ("pkg/use.py", "pkg/cmp.py", "pkg/away.py"):
        assert read(root, rel) == PROJECT[rel].replace('"edit_model"', '"edit_master"')
    for rel in ("pkg/loose.py", "pkg/strs.py", "pkg/clean.py", "pkg/lonely.py"):
        assert read(root, rel) == PROJECT[rel]


def test_before_is_pulled_once_and_only_after_a_round_flags_the_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root, spy = _probe(tmp_path, PROJECT, monkeypatch)
    assert run(root, RENAME, monkeypatch, capsys)[0] == 0
    assert spy.unflagged_before == []
    assert len(spy.before) == len(set(spy.before))
    assert set(spy.before) == spy.flagged
    # An error away from the literal, a pre-existing error on it, and a typed string are flagged; a reveal-only file,
    # a file without the string and a string outside the member's reach are not.
    assert {"pkg/away.py", "pkg/loose.py", "pkg/use.py"} <= spy.flagged
    assert not {"pkg/cmp.py", "pkg/clean.py", "pkg/strs.py"} & set(spy.before)


def test_an_equal_string_outside_the_members_reach_is_still_probed_and_listed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    files = {"pkg/__init__.py": "", "pkg/kinds.py": KINDS, "pkg/use.py": USE, "pkg/strs.py": OUTSIDE}
    root, spy = _probe(tmp_path, files, monkeypatch)
    code, _out, err = run(root, RENAME, monkeypatch, capsys)
    assert (code, err) == (0, _leftover("pkg/strs.py", 1) + "\n")
    assert "pkg/strs.py" in spy.rounds[0]
    assert "pkg/strs.py" in spy.rounds[1]
    assert read(root, "pkg/strs.py") == OUTSIDE


@pytest.mark.parametrize(
    ("code", "rewritten"),
    [("reportArgumentType", False), ("reportCallIssue", True)],
    ids=["same-code", "different-code"],
)
def test_a_pre_existing_error_on_the_literal_counts_only_with_the_same_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], code: str, rewritten: bool
) -> None:
    files = {"pkg/__init__.py": "", "pkg/kinds.py": KINDS, "pkg/use.py": USE}
    start = USE.index('"edit_model"')
    root, spy = _probe(tmp_path, files, monkeypatch, inject={"pkg/use.py": [(code, start, start + len('"edit_model"'))]})
    exit_code, _out, err = run(root, RENAME, monkeypatch, capsys)
    assert exit_code == 0
    if rewritten:
        assert (err, read(root, "pkg/use.py")) == ("", USE.replace('"edit_model"', '"edit_master"'))
    else:
        assert (err, read(root, "pkg/use.py")) == (_leftover("pkg/use.py", 9) + "\n", USE)
    assert spy.unflagged_before == []
    assert "pkg/use.py" in spy.before


CONSTS = (
    'import sys\n\nif sys.argv:\n    DEFAULT = "drop"\nelse:\n'
    '    DEFAULT = "edit_model"  # pyright: ignore[reportConstantRedefinition]\n'
)
CALLER = "from pkg.consts import DEFAULT\nfrom pkg.use import f\n\nf(DEFAULT)\n"


def test_a_new_error_in_a_file_without_the_string_is_a_blind_spot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    files = {"pkg/__init__.py": "", "pkg/kinds.py": KINDS, "pkg/use.py": USE, "pkg/consts.py": CONSTS,
             "pkg/caller.py": CALLER}
    # pkg/consts.py carries a pre-existing error keyed exactly like caller.py's new one: each file has its own `before`.
    start = CALLER.index("DEFAULT)")
    root, spy = _probe(tmp_path, files, monkeypatch,
                       inject={"pkg/consts.py": [("reportArgumentType", start, start + len("DEFAULT"))]})
    before = file_tree(root)
    code, out, err = run(root, RENAME, monkeypatch, capsys)
    assert (code, out) == (1, "")
    assert err.splitlines()[0] == message("refactor.literal-unresolved", path="pkg/caller.py", line=4, old="edit_model")
    assert len(err.splitlines()) == 2
    assert file_tree(root) == before
    assert spy.unflagged_before == []
    assert "pkg/caller.py" in spy.before


SHIM = "def f(kind: str) -> None:\n    print(kind)\n"
SHIM_STUB = "from pkg.use import f as f\n"
VIA_STUB = 'from shim import f\n\nf("edit_model")\n'


def test_a_stub_carries_the_type_but_is_never_opened_nor_pulled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    files = {"pkg/__init__.py": "", "pkg/kinds.py": KINDS, "pkg/use.py": USE, "shim.py": SHIM, "shim.pyi": SHIM_STUB,
             "app/via_stub.py": VIA_STUB}
    root, spy = _probe(tmp_path, files, monkeypatch)
    assert run(root, RENAME, monkeypatch, capsys)[::2] == (0, "")
    assert read(root, "app/via_stub.py") == VIA_STUB.replace('"edit_model"', '"edit_master"')
    assert [rel for rel in [*spy.opened, *spy.pulled] if rel.endswith(".pyi")] == []
