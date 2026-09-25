from pathlib import Path

import pytest

from living_architecture.config import (
    CONFIG_FILENAME,
    DEFAULT_ISSUE_KEY_PATTERN,
    ConfigError,
    LaConfig,
    find_repo_root,
    load_config,
)


def _write(root: Path, text: str) -> None:
    (root / CONFIG_FILENAME).write_text(text, encoding="utf-8")


def test_missing_file_gives_defaults(tmp_path: Path) -> None:
    cfg = load_config(tmp_path)
    assert cfg == LaConfig()
    assert cfg.reviewers.coderabbit is False
    assert cfg.reviewers.sonar.enabled is False
    assert cfg.issue_key_pattern == DEFAULT_ISSUE_KEY_PATTERN
    assert cfg.conventions.text_ratio_max == 0.15


def test_empty_file_gives_defaults(tmp_path: Path) -> None:
    _write(tmp_path, "")
    assert load_config(tmp_path) == LaConfig()


def test_full_config_parses(tmp_path: Path) -> None:
    _write(
        tmp_path,
        """
reviewers:
  coderabbit: true
  sonar: {enabled: true, project_key: org_proj}
issue_key_pattern: "PROJ-\\\\d+"
commands: {test: "pytest -q", lint: "ruff check ."}
conventions: {text_ratio_max: 0.2, text_ratio_exempt: [pkg/server.py]}
""",
    )
    cfg = load_config(tmp_path)
    assert cfg.reviewers.coderabbit is True
    assert cfg.reviewers.sonar.project_key == "org_proj"
    assert cfg.issue_key_re().fullmatch("PROJ-12")
    assert cfg.commands.test == "pytest -q"
    assert cfg.conventions.text_ratio_exempt == ["pkg/server.py"]


def test_sonar_enabled_requires_project_key(tmp_path: Path) -> None:
    _write(tmp_path, "reviewers: {sonar: {enabled: true}}\n")
    with pytest.raises(ConfigError, match="project_key"):
        load_config(tmp_path)


def test_unknown_key_rejected(tmp_path: Path) -> None:
    _write(tmp_path, "reviewers: {coderabit: true}\n")
    with pytest.raises(ConfigError, match="coderabit"):
        load_config(tmp_path)


def test_bad_regex_rejected(tmp_path: Path) -> None:
    _write(tmp_path, "issue_key_pattern: '[A-Z'\n")
    with pytest.raises(ConfigError, match="issue_key_pattern"):
        load_config(tmp_path)


def test_text_ratio_bounds(tmp_path: Path) -> None:
    _write(tmp_path, "conventions: {text_ratio_max: 0}\n")
    with pytest.raises(ConfigError):
        load_config(tmp_path)


def test_invalid_yaml_rejected(tmp_path: Path) -> None:
    _write(tmp_path, "reviewers: [\n")
    with pytest.raises(ConfigError, match="invalid YAML"):
        load_config(tmp_path)


def test_non_mapping_rejected(tmp_path: Path) -> None:
    _write(tmp_path, "- a\n- b\n")
    with pytest.raises(ConfigError, match="mapping"):
        load_config(tmp_path)


def test_default_issue_key_pattern() -> None:
    rx = LaConfig().issue_key_re()
    assert rx.fullmatch("ABC-123")
    assert rx.fullmatch("A1-7")
    assert not rx.fullmatch("abc-123")
    assert not rx.fullmatch("ABC123")


def test_find_repo_root_walks_up(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)
    assert find_repo_root(nested) == tmp_path.resolve()


def test_find_repo_root_falls_back_to_start(tmp_path: Path) -> None:
    nested = tmp_path / "x"
    nested.mkdir()
    if any((p / ".git").exists() for p in nested.resolve().parents):
        pytest.skip("tmp dir lives inside a git checkout")
    assert find_repo_root(nested) == nested.resolve()
