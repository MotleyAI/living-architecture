"""Python `dr-mock-lint --base BRANCH`: only the findings the base branch lacks."""

from __future__ import annotations

from pathlib import Path

import pytest

from deterministic_refactor.cli.dr_mock_lint import dr_mock_lint
from deterministic_refactor.contract import message
from refactor_cli import git

BASE = "from unittest.mock import Mock\n\n\ndef test_a() -> None:\n    Mock()\n"
MOVED_AND_ADDED = (
    "from unittest.mock import Mock\n\nX = 1\nY = 2\n\n\ndef test_a() -> None:\n    Mock()\n    Mock()\n"
)


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A repo whose `main` (pushed to a local `origin`) holds `tests/test_a.py` as BASE, on branch `feat`."""
    root = tmp_path / "repo"
    (root / "tests").mkdir(parents=True)
    (root / "tests" / "test_a.py").write_text(BASE, encoding="utf-8")
    git(root, "init", "-q", "-b", "main")
    git(root, "add", "tests/test_a.py")
    git(root, "commit", "-q", "-m", "base")
    git(tmp_path, "init", "-q", "--bare", "origin.git")
    git(root, "remote", "add", "origin", str(tmp_path / "origin.git"))
    git(root, "push", "-q", "origin", "main")
    git(root, "checkout", "-q", "-b", "feat")
    monkeypatch.chdir(root)
    return root


def _lint(*argv: str) -> int:
    try:
        return dr_mock_lint(list(argv))
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 2


def _mock(line: int, call: str = "Mock", path: str = "tests/test_a.py") -> str:
    return message("mock-lint.mock", path=path, line=line, call=call)


def test_only_new_findings(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (repo / "tests" / "test_a.py").write_text(MOVED_AND_ADDED, encoding="utf-8")
    assert _lint("--base", "main", "tests/test_a.py") == 1
    assert capsys.readouterr() == (f"{_mock(9)}\n", "")


def test_committed_change(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (repo / "tests" / "test_a.py").write_text(MOVED_AND_ADDED, encoding="utf-8")
    git(repo, "commit", "-q", "-am", "change")
    assert _lint("--base", "main", "tests") == 1
    assert capsys.readouterr() == (f"{_mock(9)}\n", "")


def test_unchanged_findings_print_nothing(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert _lint("--base", "main", "tests/test_a.py") == 0
    assert capsys.readouterr() == ("", "")


def test_renamed_file(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    git(repo, "mv", "tests/test_a.py", "tests/test_b.py")
    git(repo, "commit", "-q", "-m", "rename")
    assert _lint("--base", "main", "tests/test_b.py") == 0
    assert capsys.readouterr() == ("", "")


def test_new_file_reports_every_finding(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (repo / "tests" / "test_new.py").write_text(BASE, encoding="utf-8")
    assert _lint("--base", "main", "tests/test_new.py") == 1
    assert capsys.readouterr() == (f"{_mock(5, path='tests/test_new.py')}\n", "")


def test_a_changed_parameter_is_a_new_finding(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (repo / "tests" / "test_a.py").write_text(BASE.replace("Mock", "MagicMock"), encoding="utf-8")
    assert _lint("--base", "main", "tests/test_a.py") == 1
    assert capsys.readouterr() == (f"{_mock(5, 'MagicMock')}\n", "")


def test_unresolvable_base_exits_2(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert _lint("--base", "nope", "tests/test_a.py") == 2
    assert capsys.readouterr().out == ""


def test_failed_fetch_uses_the_ref_as_it_stands(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    git(repo, "remote", "set-url", "origin", str(repo.parent / "gone.git"))
    (repo / "tests" / "test_a.py").write_text(MOVED_AND_ADDED, encoding="utf-8")
    assert _lint("--base", "main", "tests/test_a.py") == 1
    assert capsys.readouterr().out == f"{_mock(9)}\n"


def test_without_base_every_finding(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (repo / "tests" / "test_a.py").write_text(MOVED_AND_ADDED, encoding="utf-8")
    assert _lint("tests/test_a.py", "--base", "main") == 1
    out = capsys.readouterr().out
    assert _lint("tests/test_a.py") == 1
    assert capsys.readouterr().out == f"{_mock(8)}\n{_mock(9)}\n"
    assert out == f"{_mock(9)}\n"
