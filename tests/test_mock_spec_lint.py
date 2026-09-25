from pathlib import Path

import pytest

from deterministic_refactor.mock_spec_lint import check_file, main


def _lint(tmp_path: Path, source: str) -> list[str]:
    path = tmp_path / "t.py"
    path.write_text(source)
    return check_file(path)


@pytest.mark.parametrize(
    "source",
    [
        "Mock()",
        "m.MagicMock()",
        "AsyncMock(return_value=1)",
        "NonCallableMock()",
        "patch('a.b')",
        "mock.patch('a.b')",
        "patch.object(X, 'm')",
        "patch.multiple('a', b=1)",
    ],
)
def test_flagged(tmp_path: Path, source: str) -> None:
    assert len(_lint(tmp_path, source + "\n")) == 1


@pytest.mark.parametrize(
    "source",
    [
        "Mock(spec=X)",
        "MagicMock(spec_set=X)",
        "patch('a.b', autospec=True)",
        "patch('a.b', new=1)",
        "patch('a.b', new_callable=list)",
        "patch('a.b', 1)",
        "patch.object(X, 'm', autospec=True)",
        "patch.object(X, 'm', 1)",
        "create_autospec(X)",
    ],
)
def test_allowed(tmp_path: Path, source: str) -> None:
    assert _lint(tmp_path, source + "\n") == []


def test_message_has_location(tmp_path: Path) -> None:
    [msg] = _lint(tmp_path, "x = 1\nMock()\n")
    assert msg.startswith(f"{tmp_path / 't.py'}:2: Mock()")


def test_main_exit_codes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "clean.py").write_text("Mock(spec=X)\n")
    assert main([str(tmp_path / "pkg")]) == 0
    (tmp_path / "pkg" / "bad.py").write_text("Mock()\n")
    assert main([str(tmp_path / "pkg")]) == 1
    assert "bad.py:1" in capsys.readouterr().out
    assert main([]) == 2
