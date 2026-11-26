"""The config resolver: root and stealth config files, and the stealth directories under the git common dir."""

import subprocess
from pathlib import Path

import pytest

from trmv.config import ConfigError, ConfigFile, find_config, stealth_dir

GIT_ENV = ["-c", "user.name=t", "-c", "user.email=t@example.com", "-c", "protocol.file.allow=always"]


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *GIT_ENV, *args], cwd=cwd, check=True, capture_output=True)


def _write(path: Path, text: str = "format: 0.14.0\n") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = (tmp_path / "repo").resolve()
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _write(root / "README.md", "demo\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "init")
    return root


def test_stealth_dirs_live_under_the_common_dir(repo: Path) -> None:
    assert stealth_dir(repo, "la") == repo / ".git" / "living-architecture"
    assert stealth_dir(repo, "trmv") == repo / ".git" / "trmv"


def test_stealth_dir_from_a_subdirectory_is_the_repos(repo: Path) -> None:
    sub = repo / "sub" / "dir"
    sub.mkdir(parents=True)
    assert stealth_dir(sub, "la") == repo / ".git" / "living-architecture"


def test_linked_worktree_shares_the_common_dir(repo: Path, tmp_path: Path) -> None:
    wt = tmp_path / "wt"
    _git(repo, "worktree", "add", "-q", "-b", "feat", str(wt))
    stealth = _write(repo / ".git" / "living-architecture" / "living-architecture.yaml")
    assert stealth_dir(wt.resolve(), "la") == repo / ".git" / "living-architecture"
    assert find_config(wt.resolve(), "la") == ConfigFile(path=stealth, stealth=True)


def test_submodule_has_its_own_stealth_dir(repo: Path, tmp_path: Path) -> None:
    source = tmp_path / "sub-src"
    source.mkdir()
    _git(source, "init", "-q", "-b", "main")
    _write(source / "s.txt", "s\n")
    _git(source, "add", "-A")
    _git(source, "commit", "-q", "-m", "init")
    _git(repo, "submodule", "add", "-q", str(source), "sub")
    _write(repo / ".git" / "living-architecture" / "living-architecture.yaml")
    assert stealth_dir(repo / "sub", "la") == repo / ".git" / "modules" / "sub" / "living-architecture"
    assert find_config(repo / "sub", "la") is None


def test_outside_git_there_is_no_stealth_dir(tmp_path: Path) -> None:
    root = tmp_path.resolve()
    committed = _write(root / "living-architecture.yaml")
    assert stealth_dir(root, "la") is None
    assert find_config(root, "la") == ConfigFile(path=committed, stealth=False)


def test_no_config_file(repo: Path) -> None:
    assert find_config(repo, "trmv") is None
    assert find_config(repo, "la") is None


@pytest.mark.parametrize(
    ("rel", "package"),
    [
        ("trmv.yaml", "trmv"),
        ("living-architecture.yaml", "trmv"),
        (".git/trmv/trmv.yaml", "trmv"),
        (".git/living-architecture/living-architecture.yaml", "trmv"),
        ("living-architecture.yaml", "la"),
        (".git/living-architecture/living-architecture.yaml", "la"),
    ],
)
def test_the_single_file_present_is_read(repo: Path, rel: str, package: str) -> None:
    path = _write(repo / rel)
    assert find_config(repo, package) == ConfigFile(path=path, stealth=rel.startswith(".git/"))


def test_la_reads_no_trmv_file(repo: Path) -> None:
    _write(repo / ".git" / "trmv" / "trmv.yaml")
    assert find_config(repo, "la") is None


@pytest.mark.parametrize(
    "rels",
    [
        ["living-architecture.yaml", ".git/living-architecture/living-architecture.yaml"],
        ["trmv.yaml", ".git/trmv/trmv.yaml"],
        [".git/trmv/trmv.yaml", ".git/living-architecture/living-architecture.yaml"],
        ["living-architecture.yaml", ".git/trmv/trmv.yaml", ".git/living-architecture/living-architecture.yaml"],
    ],
)
@pytest.mark.parametrize("package", ["trmv", "la"])
def test_more_than_one_file_names_every_file_in_lookup_order(repo: Path, rels: list[str], package: str) -> None:
    for rel in rels:
        _write(repo / rel)
    named = ", ".join(rel if not rel.startswith(".git/") else str(repo / rel) for rel in rels)
    with pytest.raises(ConfigError) as exc:
        find_config(repo, package)
    assert str(exc.value) == f"more than one config file applies ({named}); keep one"


def test_a_stealth_path_that_is_not_a_regular_file_is_absent(repo: Path) -> None:
    (repo / ".git" / "living-architecture" / "living-architecture.yaml").mkdir(parents=True)
    assert find_config(repo, "la") is None
