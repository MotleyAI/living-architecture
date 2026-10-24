"""The README's architecture-check route and the quickstart walkthrough run as documented."""

import re
import shutil
from collections.abc import Callable
from pathlib import Path

import pytest

from living_architecture import cli

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
QUICKSTART = REPO_ROOT / "examples" / "quickstart"
CONSOLE_BLOCK_RE = re.compile(r"^```console\n(.*?)^```$", re.MULTILINE | re.DOTALL)
COMMANDS: dict[str, Callable[[list[str]], int]] = {
    "la-arch-check": cli.la_arch_check,
    "la-arch-diagrams": cli.la_arch_diagrams,
    "la-arch-migrate": cli.la_arch_migrate,
    "la-arch-scaffold": cli.la_arch_scaffold,
}
FENCED_BLOCK_RE = re.compile(r"^```\w*\n(.*?)^```$", re.MULTILINE | re.DOTALL)
API = "src/shop/api/__init__.py"
MODEL = "architecture/model.c4"
INDEX = "architecture/index.yaml"
ARROWS = "    api -> core\n    core -> store\n"
LEGACY_ARROW = "    api -> store #legacy\n"


def _console_blocks(readme: Path = QUICKSTART / "README.md") -> list[list[tuple[str, str]]]:
    """Each console block as (command, expected output) pairs, `cd` lines dropped."""
    text = readme.read_text(encoding="utf-8")
    blocks = []
    for body in CONSOLE_BLOCK_RE.findall(text):
        steps: list[tuple[str, str]] = []
        for line in body.splitlines(keepends=True):
            if line.startswith("$ "):
                steps.append((line[2:].strip(), ""))
            else:
                command, output = steps[-1]
                steps[-1] = (command, output + line)
        blocks.append([step for step in steps if not step[0].startswith("cd ")])
    return blocks


def _edit(root: Path, rel: str, old: str, new: str) -> None:
    path = root / rel
    text = path.read_text(encoding="utf-8")
    assert old in text, f"{rel} lacks {old!r}"
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def _remove_shortcut(root: Path) -> None:
    _edit(root, API, "from shop.store import save\n", "")
    _edit(root, API, "\n\ndef post_order_fast(item: str) -> str:\n    return save(item)\n", "")


def _add_legacy_arrow(root: Path) -> None:
    _edit(root, MODEL, ARROWS, ARROWS + LEGACY_ARROW)


def _raise_baseline(root: Path) -> None:
    _edit(root, INDEX, "{baseline: 0}", "{baseline: 1}")


def _refresh_diagrams(root: Path) -> None:
    assert cli.la_arch_diagrams(["--root", str(root)]) == 0


def _run(command: str, capsys: pytest.CaptureFixture[str]) -> tuple[int, str]:
    name, *args = command.split()
    rc = COMMANDS[name](args)
    return rc, capsys.readouterr().out


@pytest.fixture
def example(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "quickstart"
    shutil.copytree(QUICKSTART, root)
    monkeypatch.chdir(root)
    return root


def test_readme_has_the_walkthrough_blocks() -> None:
    assert [len(block) for block in _console_blocks()] == [1, 1, 1, 2, 1]


# The README's console blocks in order, each with the edits that lead to it from the shipped example.
WALKTHROUGH: list[tuple[list[Callable[[Path], None]], list[int]]] = [
    ([], [1]),
    ([_remove_shortcut], [0]),
    ([_add_legacy_arrow], [1]),
    ([_add_legacy_arrow, _raise_baseline], [0, 0]),
    ([_add_legacy_arrow, _raise_baseline, _refresh_diagrams, _remove_shortcut], [1]),
]


@pytest.mark.parametrize("index", range(len(WALKTHROUGH)))
def test_console_block_is_the_real_output(index: int, example: Path, capsys: pytest.CaptureFixture[str]) -> None:
    edits, exit_codes = WALKTHROUGH[index]
    for edit in edits:
        edit(example)
    capsys.readouterr()
    steps = _console_blocks()[index]
    assert [_run(command, capsys) for command, _ in steps] == [
        (code, output) for code, (_, output) in zip(exit_codes, steps, strict=True)
    ]


def test_dropping_the_dead_arrow_passes(example: Path, capsys: pytest.CaptureFixture[str]) -> None:
    for edit in (_add_legacy_arrow, _raise_baseline, _refresh_diagrams, _remove_shortcut):
        edit(example)
    _edit(example, MODEL, LEGACY_ARROW, "")
    _edit(example, INDEX, "{baseline: 1}", "{baseline: 0}")
    _refresh_diagrams(example)
    capsys.readouterr()
    assert _run("la-arch-check --root .", capsys) == (0, "arch_check: OK\n")


# The root README's console blocks, in order, as the WALKTHROUGH steps that produce them: the shortcut import,
# then the legacy arrow left after its import is gone.
ROOT_README_STEPS = [0, 4]


def test_root_readme_shows_the_walkthrough_outputs_of_its_scenarios() -> None:
    walkthrough = _console_blocks()
    shown = [(command, output) for [(command, output)] in _console_blocks(REPO_ROOT / "README.md")]
    expected = [walkthrough[step][-1] for step in ROOT_README_STEPS]
    assert shown == [(command.removesuffix(" --root ."), output) for command, output in expected]


def test_shipped_example_matches_its_diagram(example: Path) -> None:
    before = (example / "architecture" / "system.arc42.md").read_text(encoding="utf-8")
    _refresh_diagrams(example)
    assert (example / "architecture" / "system.arc42.md").read_text(encoding="utf-8") == before


def _readme_route_blocks() -> list[str]:
    """The fenced blocks of the root README's "Just the architecture check" route, before its CI snippet."""
    text = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    route = text.split("### Just the architecture check\n", 1)[1].split("Pin the check in CI", 1)[0]
    return FENCED_BLOCK_RE.findall(route)


def test_readme_route_ends_in_a_passing_check(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    index, config, commands = _readme_route_blocks()
    shutil.copytree(QUICKSTART / "src", tmp_path / "src")
    (tmp_path / "architecture").mkdir()
    (tmp_path / INDEX).write_text(index.replace("mypkg", "shop"), encoding="utf-8")
    (tmp_path / "living-architecture.yaml").write_text(config, encoding="utf-8")
    exit_codes = []
    for line in commands.splitlines():
        name = line.split("#", 1)[0].strip()
        exit_codes.append(COMMANDS[name](["--root", str(tmp_path)]))
    assert exit_codes == [0, 0, 0]
    assert capsys.readouterr().out.endswith("arch_check: OK\n")
    assert "format:" in (tmp_path / "living-architecture.yaml").read_text(encoding="utf-8")
