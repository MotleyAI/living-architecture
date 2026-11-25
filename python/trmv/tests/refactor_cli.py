"""Drivers for the `trmv-refactor` CLI tests: run a command, locate text, compare two runs."""

import os
import re
import subprocess
import sys
from pathlib import Path
from typing import NamedTuple

import pytest

from project_files import file_tree, write_project
from trmv.cli.trmv_refactor import trmv_refactor
from trmv.config import current_format
from trmv.contract import message

BIN_DIR = Path(sys.executable).parent

Result = tuple[int, str, str]

_PHASES = "resolve|checks|references|rules|conflicts|baseline|write"
_PROGRESS = re.compile(rf"\[(?:{_PHASES})\]|\[(?:{_PHASES}) \d+/\d+\] .*")


def final_report(err: str) -> str:
    """`trmv-refactor`'s stderr without its phase and progress lines: every refusal, in the order printed."""
    return "".join(line for line in err.splitlines(keepends=True) if not _PROGRESS.fullmatch(line.rstrip("\n")))


def entry_refusal(locator: str, text: str, *indexes: int) -> str:
    """`text` as the refusal of the map entries `indexes` (entry 1 by default) located by `locator`."""
    if len(indexes) > 1:
        entries = message("refactor.progress-entries", indexes=", ".join(str(i) for i in indexes))
    else:
        entries = message("refactor.progress-entry", index=indexes[0] if indexes else 1)
    return message("refactor.entry-refusal", entries=entries, locator=locator, text=text)


def run_raw(root: Path, argv: list[str], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> Result:
    """`trmv-refactor --project root ARGV` from `root`, its stderr whole; a usage error comes back as exit 2."""
    monkeypatch.chdir(root)
    try:
        code = trmv_refactor(["--project", str(root), *argv])
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else 2
    out, err = capsys.readouterr()
    return code, out, err


def run(root: Path, argv: list[str], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> Result:
    """`run_raw` with its stderr reduced to the `final_report`."""
    code, out, err = run_raw(root, argv, monkeypatch, capsys)
    return code, out, final_report(err)


def line_col(root: Path, rel: str, needle: str, nth: int = 0) -> list[str]:
    """`--line L --col C` (1-based) of the `nth` occurrence of `needle` in `rel`."""
    text = (root / rel).read_text(encoding="utf-8")
    offset = -1
    for _ in range(nth + 1):
        offset = text.index(needle, offset + 1)
    line = text.count("\n", 0, offset) + 1
    col = offset - (text.rfind("\n", 0, offset) + 1) + 1
    return ["--line", str(line), "--col", str(col)]


def read(root: Path, rel: str) -> str:
    return (root / rel).read_text(encoding="utf-8")


def assert_same_run(
    tmp_path: Path,
    files: dict[str, str],
    reference: list[str],
    candidate: list[str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    *,
    extra: dict[str, str] | None = None,
) -> Path:
    """Run `reference` and `candidate` on two copies of `files`; both must agree and the reference must succeed."""
    left = write_project(tmp_path / "left", files)
    right = write_project(tmp_path / "right", {**files, **(extra or {})})
    before = file_tree(left)
    expected = run(left, reference, monkeypatch, capsys)
    actual = run(right, candidate, monkeypatch, capsys)
    assert expected[0] == 0, f"reference run failed: {expected}"
    assert file_tree(left) != before, "reference run changed nothing"
    assert actual == expected, f"runs differ:\n{actual}\n!=\n{expected}"
    for rel in extra or {}:
        (right / rel).unlink()
    assert file_tree(right) == file_tree(left), "trees differ"
    return right


def template_regex(text: str, **wild: str) -> re.Pattern[str]:
    """`text` as a full-match pattern in which each `wild` value matches anything."""
    pattern = re.escape(text)
    for value in wild.values():
        pattern = pattern.replace(re.escape(value), ".+")
    return re.compile(pattern)


def git(root: Path, *args: str) -> str:
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@t"}
    return subprocess.run(["git", *args], cwd=root, env=env, capture_output=True, text=True, check=True).stdout


def git_project(root: Path, files: dict[str, str], config: str | None = None) -> Path:
    """`write_project` as a git repo (prose files come from git); `config` is appended to a repo config."""
    extra = {} if config is None else {"living-architecture.yaml": f"format: {current_format('living-architecture.yaml')}\n{config}"}
    write_project(root, {**files, **extra})
    git(root, "init", "-q", "-b", "main")
    return root


def rename_argv(rel: str, symbol: str, new_name: str, *flags: str, apply: bool = True) -> list[str]:
    """`trmv-refactor`'s arguments for a rename located by `--symbol`."""
    return [*(["--apply"] if apply else []), "rename", "--file", rel, "--symbol", symbol, "--new-name", new_name, *flags]


def leftover(path: str, line: int, where: str, old: str) -> str:
    return message("refactor.leftover", path=path, line=line, where=where, old=old)


def configure_typecheck(root: Path, command: str | None) -> None:
    """A git repo at `root` whose config sets `commands.typecheck.python` (YAML null for None)."""
    if not (root / ".git").exists():
        git(root, "init", "-q", "-b", "main")
    value = "null" if command is None else command
    (root / "living-architecture.yaml").write_text(
        f"format: {current_format('living-architecture.yaml')}\ncommands: {{typecheck: {{python: {value}}}}}\n", encoding="utf-8"
    )


class Captured(NamedTuple):
    out: str
    err: str


def readouterr(capsys: pytest.CaptureFixture[str]) -> Captured:
    """`capsys.readouterr()` with `trmv-refactor`'s stderr reduced to the `final_report`."""
    out, err = capsys.readouterr()
    return Captured(out, final_report(err))
