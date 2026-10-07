"""Repo languages: an explicit typecheck command, or a root marker plus a counted file of the language."""

import subprocess
from pathlib import Path

import pytest

from living_architecture.config import ConfigError, load_config, repo_languages
from living_architecture.contract import message


def _repo(root: Path, files: dict[str, str]) -> list[str]:
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=root, check=True)
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")
    return repo_languages(root, load_config(root))


def test_stray_script_is_not_a_language(tmp_path: Path) -> None:
    assert _repo(tmp_path, {"pyproject.toml": "", "a.py": "X = 1\n", "docs/static/app.js": "x;\n"}) == ["python"]


def test_typecheck_null_keeps_the_language(tmp_path: Path) -> None:
    files = {"tsconfig.json": "{}", "src/a.ts": "export {};\n",
             "living-architecture.yaml": "commands: {typecheck: {typescript: null}}\n"}
    assert _repo(tmp_path, files) == ["typescript"]


def test_explicit_entry_forces_the_language(tmp_path: Path) -> None:
    files = {"living-architecture.yaml": "commands: {typecheck: {python: basedpyright -p python}}\n"}
    assert _repo(tmp_path, files) == ["python"]


def test_both_languages_in_registry_order(tmp_path: Path) -> None:
    files = {"tsconfig.json": "{}", "web/a.ts": "export {};\n", "setup.py": "", "pkg/a.py": "X = 1\n"}
    assert _repo(tmp_path, files) == ["python", "typescript"]


def test_marker_without_files(tmp_path: Path) -> None:
    assert _repo(tmp_path, {"pyproject.toml": "", "README.md": "x\n"}) == []


def test_exempt_and_ignored_files_do_not_count(tmp_path: Path) -> None:
    files = {"tsconfig.json": "{}", "gen/a.ts": "export {};\n", "out/b.ts": "export {};\n", ".gitignore": "out/\n",
             "living-architecture.yaml": "conventions: {exempt: ['gen/*']}\n"}
    assert _repo(tmp_path, files) == []


def test_tracked_file_counts_even_when_ignored(tmp_path: Path) -> None:
    files = {"tsconfig.json": "{}", "out/b.ts": "export {};\n"}
    for rel, text in files.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(text, encoding="utf-8")
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "out/b.ts"], cwd=tmp_path, check=True)
    (tmp_path / ".gitignore").write_text("out/\n", encoding="utf-8")
    assert repo_languages(tmp_path, load_config(tmp_path)) == ["typescript"]


def _without_git(root: Path, monkeypatch: pytest.MonkeyPatch, *, repo: bool) -> None:
    (root / "pyproject.toml").write_text("", encoding="utf-8")
    (root / "a.py").write_text("X = 1\n", encoding="utf-8")
    if repo:
        (root / ".git").mkdir()
    monkeypatch.setenv("PATH", str(root / "no-bin"))


def test_git_missing_inside_a_repo_is_an_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _without_git(tmp_path, monkeypatch, repo=True)
    config = load_config(tmp_path)
    with pytest.raises(ConfigError, match=message("config.git-failed")):
        repo_languages(tmp_path, config)


def test_git_missing_outside_a_repo_lists_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _without_git(tmp_path, monkeypatch, repo=False)
    assert repo_languages(tmp_path, load_config(tmp_path)) == []
