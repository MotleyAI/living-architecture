"""The console outputs and the architecture-check route in docs/how-it-works.md run as documented."""

import re
import shutil
from collections.abc import Callable
from pathlib import Path

import pytest

from living_architecture import cli

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
HOW_IT_WORKS = REPO_ROOT / "docs" / "how-it-works.md"
SHOP = Path(__file__).resolve().parent / "fixtures" / "shop"
CONSOLE_BLOCK_RE = re.compile(r"^```console\n(.*?)^```$", re.MULTILINE | re.DOTALL)
FENCED_BLOCK_RE = re.compile(r"^```\w*\n(.*?)^```$", re.MULTILINE | re.DOTALL)
COMMANDS: dict[str, Callable[[list[str]], int]] = {
    "la-arch-check": cli.la_arch_check,
    "la-arch-diagrams": cli.la_arch_diagrams,
    "la-arch-migrate": cli.la_arch_migrate,
    "la-arch-scaffold": cli.la_arch_scaffold,
}
API = "src/shop/api/__init__.py"
MODEL = "architecture/model.c4"
INDEX = "architecture/index.yaml"
ARROWS = "    api -> core\n    core -> store\n"
LEGACY_ARROW = "    api -> store #legacy\n"


def _console_blocks() -> list[tuple[str, str]]:
    """Each console block as its one (command, expected output) pair."""
    blocks = []
    for body in CONSOLE_BLOCK_RE.findall(HOW_IT_WORKS.read_text(encoding="utf-8")):
        command, output = body.split("\n", 1)
        assert command.startswith("$ ")
        blocks.append((command.removeprefix("$ "), output))
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


@pytest.fixture
def shop(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "shop"
    shutil.copytree(SHOP, root)
    monkeypatch.chdir(root)
    return root


# The doc's console blocks in order, each with the edits that lead to it from the fixture: the shortcut import, then
# the arrow left behind after its import is gone.
SCENARIOS: list[list[Callable[[Path], None]]] = [
    [],
    [_add_legacy_arrow, _raise_baseline, _refresh_diagrams, _remove_shortcut],
]


def test_doc_has_one_console_block_per_scenario() -> None:
    assert len(_console_blocks()) == len(SCENARIOS)


@pytest.mark.parametrize("index", range(len(SCENARIOS)))
def test_console_block_is_the_real_output(index: int, shop: Path, capsys: pytest.CaptureFixture[str]) -> None:
    for edit in SCENARIOS[index]:
        edit(shop)
    capsys.readouterr()
    command, output = _console_blocks()[index]
    name, *args = command.split()
    assert COMMANDS[name](args) == 1
    assert capsys.readouterr().out == output


def test_fixture_matches_its_diagram(shop: Path) -> None:
    before = (shop / "architecture" / "system.arc42.md").read_text(encoding="utf-8")
    _refresh_diagrams(shop)
    assert (shop / "architecture" / "system.arc42.md").read_text(encoding="utf-8") == before


def _route_blocks() -> list[str]:
    """The fenced blocks of the doc's "Just the architecture check" route, before its CI snippet."""
    text = HOW_IT_WORKS.read_text(encoding="utf-8")
    route = text.split("## Just the architecture check\n", 1)[1].split("Pin the check in CI", 1)[0]
    return FENCED_BLOCK_RE.findall(route)


def test_route_ends_in_a_passing_check(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    index, config, commands = _route_blocks()
    shutil.copytree(SHOP / "src", tmp_path / "src")
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
