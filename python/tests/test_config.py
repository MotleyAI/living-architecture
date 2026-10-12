from pathlib import Path

import pytest

from living_architecture.config import (
    CONFIG_FILENAME,
    ConfigError,
    explicit_typecheck,
    find_repo_root,
    load_config,
    load_raw,
    resolve,
)
from living_architecture.contract import config_file, local_config_file

DEFAULT_ISSUE_KEY_PATTERN = r"[A-Z][A-Z0-9]+-\d+"


def _write(root: Path, text: str) -> None:
    (root / CONFIG_FILENAME).write_text(text, encoding="utf-8")


def test_missing_file_gives_defaults(tmp_path: Path) -> None:
    cfg = load_config(tmp_path)
    assert cfg == resolve(None)
    assert cfg.tracker == "linear"
    assert cfg.openspec is True
    assert cfg.architecture is False
    assert cfg.reviewers.codex is True
    assert cfg.reviewers.sonar.project_key is None
    assert cfg.conventions.rules == ["import-not-top", "text-ratio", "composite-assert", "raises-single-throw"]
    assert cfg.issue_key_pattern == DEFAULT_ISSUE_KEY_PATTERN
    assert cfg.conventions.text_ratio_max == 0.15


def test_empty_file_gives_defaults(tmp_path: Path) -> None:
    _write(tmp_path, "")
    assert load_config(tmp_path) == resolve(None)


def test_full_config_parses(tmp_path: Path) -> None:
    _write(
        tmp_path,
        """
tracker: github
openspec: false
architecture: true
reviewers:
  codex: false
  sonar: {project_key: org_proj}
issue_key_pattern: "PROJ-\\\\d+"
commands: {test: "pytest -q", lint: "ruff check ."}
conventions: {text_ratio_max: 0.2, exempt: [pkg/server.py], rules: [text-ratio]}
""",
    )
    cfg = load_config(tmp_path)
    assert (cfg.tracker, cfg.openspec, cfg.architecture) == ("github", False, True)
    assert cfg.reviewers.codex is False
    assert cfg.reviewers.sonar.project_key == "org_proj"
    assert cfg.issue_key_re().fullmatch("PROJ-12")
    assert cfg.commands.test == "pytest -q"
    assert cfg.conventions.exempt == ["pkg/server.py"]
    assert cfg.conventions.rules == ["text-ratio"]


@pytest.mark.parametrize(
    ("text", "offender"),
    [
        ("reviewers: {coderabbit: true}\n", "coderabbit"),
        ("reviewers: {sonar: {enabled: true, project_key: o_r}}\n", "enabled"),
        ("tracker: jira\n", "tracker"),
        ("conventions: {rules: [import-not-top, no-such-rule]}\n", "no-such-rule"),
    ],
)
def test_invalid_gate_values_rejected(tmp_path: Path, text: str, offender: str) -> None:
    _write(tmp_path, text)
    with pytest.raises(ConfigError, match=offender):
        load_config(tmp_path)


def test_explicit_falsy_gate_values_kept(tmp_path: Path) -> None:
    _write(tmp_path, "conventions: {rules: []}\nreviewers: {codex: no}\nopenspec: off\n")
    cfg = load_config(tmp_path)
    assert cfg.conventions.rules == []
    assert cfg.reviewers.codex is False
    assert cfg.openspec is False


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
    rx = resolve(None).issue_key_re()
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


# ---- living-architecture.local.yaml


def _write_local(root: Path, text: str) -> None:
    (root / local_config_file()).write_text(text, encoding="utf-8")


def _error(root: Path) -> str:
    with pytest.raises(ConfigError) as info:
        load_config(root)
    return str(info.value)


def test_local_value_overrides_committed(tmp_path: Path) -> None:
    _write(tmp_path, "tracker: github\nreviewers: {codex: true}\n")
    _write_local(tmp_path, "tracker: none\nreviewers: {codex: false}\n")
    cfg = load_config(tmp_path)
    assert (cfg.tracker, cfg.reviewers.codex) == ("none", False)


def test_local_merge_keeps_sibling_keys(tmp_path: Path) -> None:
    _write(tmp_path, "openspec: false\nreviewers: {sonar: {project_key: o_r}}\n")
    _write_local(tmp_path, "reviewers: {codex: false}\n")
    cfg = load_config(tmp_path)
    assert cfg.reviewers.codex is False
    assert cfg.reviewers.sonar.project_key == "o_r"
    assert cfg.openspec is False


def test_local_without_committed_merges_over_defaults(tmp_path: Path) -> None:
    _write_local(tmp_path, "tracker: none\n")
    assert load_config(tmp_path) == resolve({"tracker": "none"})


@pytest.mark.parametrize("text", ["", "# my overrides\n", "reviewers: {}\n"])
def test_local_without_leaf_overrides_nothing(tmp_path: Path, text: str) -> None:
    _write(tmp_path, "tracker: github\n")
    _write_local(tmp_path, text)
    assert load_config(tmp_path) == resolve({"tracker": "github"})
    assert load_raw(tmp_path).overrides == []


def test_overrides_in_schema_order_even_when_equal(tmp_path: Path) -> None:
    _write(tmp_path, "tracker: github\n")
    _write_local(tmp_path, "reviewers: {codex: false}\ntracker: github\n")
    assert load_raw(tmp_path).overrides == ["tracker", "reviewers.codex"]


def test_raw_data_is_the_merge(tmp_path: Path) -> None:
    _write(tmp_path, "tracker: github\nreviewers: {sonar: {project_key: o_r}}\n")
    _write_local(tmp_path, "reviewers: {codex: false}\n")
    assert load_raw(tmp_path).data == {"tracker": "github", "reviewers": {"sonar": {"project_key": "o_r"}, "codex": False}}


@pytest.mark.parametrize(("committed", "local"), [(False, False), (True, False), (False, True), (True, True)])
def test_raw_reports_which_files_exist(tmp_path: Path, committed: bool, local: bool) -> None:
    if committed:
        _write(tmp_path, "tracker: github\n")
    if local:
        _write_local(tmp_path, "tracker: none\n")
    raw = load_raw(tmp_path)
    assert (raw.has_committed, raw.has_local) == (committed, local)


def test_local_directory_counts_as_absent(tmp_path: Path) -> None:
    (tmp_path / local_config_file()).mkdir()
    assert load_raw(tmp_path).has_local is False
    assert load_config(tmp_path) == resolve(None)


@pytest.mark.parametrize(
    ("text", "key"),
    [
        ("openspec: false\n", "openspec"),
        ("reviewers: {sonar: {project_key: o_r}}\n", "sonar"),
        ("tracker: jira\n", "tracker"),
        ("tracker:\n", "tracker"),
        ("reviewers: {codex: yes please}\n", "codex"),
        ("reviewers:\n", "reviewers"),
    ],
)
def test_local_schema_error_names_key_and_local_file(tmp_path: Path, text: str, key: str) -> None:
    _write_local(tmp_path, text)
    error = _error(tmp_path)
    assert error.startswith(f"{tmp_path / local_config_file()}: ")
    assert key in error


def test_committed_yaml_checked_before_local_yaml(tmp_path: Path) -> None:
    _write(tmp_path, "reviewers: [\n")
    _write_local(tmp_path, "tracker: [\n")
    assert _error(tmp_path).startswith(f"{tmp_path / config_file()}: ")


def test_local_yaml_error_names_local_file(tmp_path: Path) -> None:
    _write(tmp_path, "tracker: github\n")
    _write_local(tmp_path, "tracker: [\n")
    assert _error(tmp_path).startswith(f"{tmp_path / local_config_file()}: ")


@pytest.mark.parametrize("text", ["- tracker\n", "42\n"])
def test_local_top_level_must_be_a_mapping(tmp_path: Path, text: str) -> None:
    _write_local(tmp_path, text)
    assert _error(tmp_path).startswith(f"{tmp_path / local_config_file()}: ")


def test_local_schema_checked_before_committed_schema(tmp_path: Path) -> None:
    _write(tmp_path, "bogus: 1\n")
    _write_local(tmp_path, "openspec: false\n")
    assert _error(tmp_path).startswith(f"{tmp_path / local_config_file()}: ")


@pytest.mark.parametrize("text", ["bogus: 1\n", "- a\n"])
def test_committed_error_with_valid_local_names_committed_file(tmp_path: Path, text: str) -> None:
    _write(tmp_path, text)
    _write_local(tmp_path, "tracker: none\n")
    assert _error(tmp_path).startswith(f"{tmp_path / config_file()}: ")


def test_explicit_typecheck_reads_the_merged_data(tmp_path: Path) -> None:
    _write(tmp_path, "commands: {typecheck: {python: basedpyright -p python}}\n")
    _write_local(tmp_path, "tracker: none\n")
    assert explicit_typecheck(tmp_path) == {"python"}
