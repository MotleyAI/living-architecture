"""la's stealth config: the stealth file loaded through trmv's resolver, its refusals, and the private store id."""

import hashlib
import subprocess
from pathlib import Path

import pytest

from living_architecture.config import ConfigError, load_config, openspec_store_id


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path.resolve()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=root, check=True, capture_output=True)
    return root


def _stealth(repo: Path, text: str) -> Path:
    path = repo / ".git" / "living-architecture" / "living-architecture.yaml"
    _write(path, "format: 0.14.0\n" + text)
    return path


def test_store_id_is_la_and_twelve_hex_digits_of_the_path_digest() -> None:
    assert openspec_store_id(Path("/x/.git/living-architecture")) == "la-e9f5a185b6df"


def test_store_id_follows_the_stealth_dir(tmp_path: Path) -> None:
    path = tmp_path.resolve() / ".git" / "living-architecture"
    expected = "la-" + hashlib.sha256(str(path).encode("utf-8")).hexdigest()[:12]
    assert openspec_store_id(path) == expected


def test_the_stealth_file_is_loaded(repo: Path) -> None:
    _stealth(repo, "tracker: none\n")
    assert load_config(repo).tracker == "none"


def test_local_file_is_refused_in_stealth(repo: Path) -> None:
    _stealth(repo, "tracker: none\n")
    _write(repo / "living-architecture.local.yaml", "tracker: github\n")
    with pytest.raises(ConfigError, match="living-architecture.local.yaml"):
        load_config(repo)


def test_architecture_is_refused_in_stealth(repo: Path) -> None:
    path = _stealth(repo, "architecture: true\n")
    with pytest.raises(ConfigError, match="architecture") as exc:
        load_config(repo)
    assert str(path) in str(exc.value)


def test_core_leak_token_is_refused(repo: Path) -> None:
    _stealth(repo, "leaks: {allow: [trmv]}\n")
    with pytest.raises(ConfigError, match="trmv"):
        load_config(repo)


def test_waivable_leak_token_is_allowed(repo: Path) -> None:
    _stealth(repo, "leaks: {allow: [arc42, pr-plan]}\n")
    assert load_config(repo).leaks.allow == ["arc42", "pr-plan"]


def test_leaks_in_a_root_file_is_refused(repo: Path) -> None:
    _write(repo / "living-architecture.yaml", "format: 0.14.0\nleaks: {allow: [arc42]}\n")
    with pytest.raises(ConfigError, match="leaks"):
        load_config(repo)
