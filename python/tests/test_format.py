"""The declared repo format: version rules, the stamp, the check, and which commands run it."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from living_architecture import config
from living_architecture.contract import load_yaml, render_template

SHARED = next(p for p in Path(__file__).resolve().parents if (p / "shared" / "vectors").is_dir()) / "shared"
VECTORS = yaml.safe_load((SHARED / "vectors" / "format.yaml").read_text(encoding="utf-8"))
MANIFEST = yaml.safe_load((SHARED / "cli.yaml").read_text(encoding="utf-8"))["commands"]
BIN_DIR = Path(sys.executable).parent
CONFIG = "living-architecture.yaml"


def _current() -> str:
    return yaml.safe_load((SHARED / "config.yaml").read_text(encoding="utf-8"))["format"]


def _message(template_id: str, **values: object) -> str:
    template = yaml.safe_load((SHARED / "findings.yaml").read_text(encoding="utf-8"))["findings"][template_id]
    return render_template(template, values)


def test_current_format_comes_from_the_contract() -> None:
    assert config.current_format() == _current()


@pytest.mark.parametrize("value", VECTORS["valid"])
def test_valid_versions(value: object) -> None:
    assert config.is_version(value)


@pytest.mark.parametrize("value", VECTORS["invalid"], ids=repr)
def test_invalid_versions(value: object) -> None:
    assert not config.is_version(value)


@pytest.mark.parametrize(("a", "b", "sign"), VECTORS["compare"], ids=lambda v: str(v))
def test_version_comparison(a: str, b: str, sign: int) -> None:
    assert (config.compare_versions(a, b), config.compare_versions(b, a)) == (sign, -sign)


@pytest.mark.parametrize("vector", VECTORS["stamp"], ids=lambda v: v["name"])
def test_stamp(vector: dict) -> None:
    expected = vector["stamped"]
    assert config.stamp_format(vector["text"]) == (None if expected is None else expected.replace("<FORMAT>", _current()))


@pytest.mark.parametrize("vector", [v for v in VECTORS["stamp"] if v["stamped"] is not None], ids=lambda v: v["name"])
def test_stamp_adds_only_the_format(vector: dict) -> None:
    before = load_yaml(vector["text"]) or {}
    assert load_yaml(config.stamp_format(vector["text"])) == {**before, "format": _current()}


def _repo(tmp_path: Path, committed: bytes | None, local: str | None = None) -> Path:
    root = tmp_path / "repo"
    root.mkdir(parents=True)
    if committed is not None:
        (root / CONFIG).write_bytes(committed)
    if local is not None:
        (root / "living-architecture.local.yaml").write_text(local, encoding="utf-8")
    return root


@pytest.mark.parametrize(
    ("committed", "local"),
    [
        (None, None),
        (None, "tracker: github\n"),
        (b"reviewers: [\n", None),
        (b"\xff\xfe not utf-8\n", None),
        (b"- a\n", None),
        (b"", None),
    ],
    ids=["no-file", "local-only", "invalid-yaml", "not-utf8", "list", "empty"],
)
def test_check_passes_files_it_cannot_judge(tmp_path: Path, committed: bytes | None, local: str | None) -> None:
    assert config.check_format(_repo(tmp_path, committed, local)) is None


def test_check_passes_an_unreadable_config(tmp_path: Path) -> None:
    root = _repo(tmp_path, None)
    (root / CONFIG).mkdir()
    assert config.check_format(root) is None


def test_check_ignores_the_local_file(tmp_path: Path) -> None:
    root = _repo(tmp_path, f"format: {_current()}\n".encode(), local="format: 9.0.0\n")
    assert config.check_format(root) is None
    other = _repo(tmp_path / "other", b"tracker: linear\n", local=f"format: {_current()}\n")
    assert config.check_format(other) == _message("format.missing", current=_current())


@pytest.mark.parametrize(
    ("text", "template_id", "values"),
    [
        ("tracker: linear\n", "format.missing", {}),
        ("format: 9.0.0\n", "format.newer", {"declared": "9.0.0"}),
        ("format: 0.0.1\n", "format.older", {"declared": "0.0.1"}),
        ("format: 0.4\n", "format.invalid", {"value": 0.4}),
        ("format:\n", "format.invalid", {"value": None}),
    ],
    ids=["missing", "newer", "older", "invalid", "null"],
)
def test_check_refusals(tmp_path: Path, text: str, template_id: str, values: dict) -> None:
    expected = _message(template_id, current=_current(), **values)
    assert config.check_format(_repo(tmp_path, text.encode())) == expected


def test_check_passes_the_current_format(tmp_path: Path) -> None:
    assert config.check_format(_repo(tmp_path, f"format: {_current()}\nbogus: 1\n".encode())) is None


# ---- every manifest command not marked exempt runs the check

# A real invocation of each command; the shims only print their help, so none reaches GitHub.
ARGV = {
    "la-config": ["show"],
    "la-doctor": [],
    "la-arch-check": [],
    "la-arch-scaffold": [],
    "la-arch-diagrams": [],
    "la-arch-migrate": [],
    "la-check-conventions": ["--base", "main"],
    "la-count-comments": ["a.py"],
    "la-typecheck": [],
    "la-fetch-coderabbit-threads": ["--help"],
    "la-reply-invalid-coderabbit": ["--help"],
    "la-reply-to-pr-thread": ["--help"],
    "la-fetch-failed-pr-checks": ["--help"],
    "la-wait-for-reviews": ["--help"],
    "la-pr-reviewers": ["--help"],
    "dr-refactor": ["rename", "--file", "a.py", "--name", "f", "--new-name", "g"],
    "dr-compliance": ["a.py"],
    "dr-mock-lint": ["a.py"],
}


def test_every_manifest_command_has_an_invocation() -> None:
    assert set(ARGV) == set(MANIFEST)


@pytest.mark.parametrize("command", sorted(MANIFEST))
def test_format_check_runs_unless_the_manifest_exempts_the_command(command: str, tmp_path: Path) -> None:
    root = _repo(tmp_path, b"tracker: linear\n")
    (root / "a.py").write_text("def f() -> None: ...\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=root, check=True)
    env = {**os.environ, "HOME": str(tmp_path), "GIT_CONFIG_NOSYSTEM": "1"}
    proc = subprocess.run([str(BIN_DIR / command), *ARGV[command]], cwd=root, env=env, capture_output=True, text=True,
                          timeout=120, check=False)
    refusal = _message("format.missing", current=_current()) + "\n"
    if command == "la-doctor":
        assert refusal not in proc.stderr
    elif MANIFEST[command].get("format") == "exempt":
        assert refusal.strip() not in proc.stdout + proc.stderr
    else:
        assert (proc.returncode, proc.stdout, proc.stderr) == (2, "", refusal)
