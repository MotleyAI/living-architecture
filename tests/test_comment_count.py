import subprocess
from pathlib import Path

import pytest

from living_architecture.comment_count import counts, main

SRC = '"""Module doc\nspanning two lines."""\n\n# a comment\ndef f():\n    """One-liner."""\n    return 1  # trailing\n'


def test_counts():
    assert counts(SRC) == (2, 3)


def test_counts_missing_and_broken():
    assert counts(None) == (0, 0)
    assert counts("# c\nx = = 1\n") == (1, 0)


def test_per_file(tmp_path, capsys):
    f = tmp_path / "m.py"
    f.write_text(SRC)
    assert main([str(f)]) == 0
    assert "TOTAL=5 (comment 2, docstring 3)" in capsys.readouterr().out


def test_range_against_git_ref(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    for args in (["init", "-q"], ["config", "user.email", "t@example.com"], ["config", "user.name", "t"]):
        subprocess.run(["git", *args], check=True)
    Path("m.py").write_text("X = 1\n")
    subprocess.run(["git", "add", "m.py"], check=True)
    subprocess.run(["git", "commit", "-q", "-m", "base"], check=True)
    Path("m.py").write_text(SRC)
    assert main(["--range", "HEAD", "m.py", "gone.py"]) == 0
    assert "NET ADDED total=5 (comment 2, docstring 3)" in capsys.readouterr().out


@pytest.mark.parametrize("argv", [[], ["--range", "HEAD"]])
def test_usage(argv):
    assert main(argv) == 2
