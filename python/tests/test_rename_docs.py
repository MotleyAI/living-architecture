"""Python `dr-refactor rename --docs`: mentions in comments, docstrings, strings and prose files."""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

from living_architecture.cli import dr_refactor
from living_architecture.contract import message

MakeProject = Callable[..., Path]
OLD, NEW = "recommend_root_model", "pick_root_model"

ENGINE = '''\
class SlayerQueryEngine:
    def recommend_root_model(self, x: int) -> str:
        """See ``recommend_root_model`` and :meth:`recommend_root_model`."""
        # then recommend_root_model runs; `recommend_root_model()` returns
        if x:
            raise ValueError(f"recommend_root_model: no candidates for {x}")
        raise ValueError("recommend_root_model: no candidates")
'''
ENGINE_AFTER = '''\
class SlayerQueryEngine:
    def pick_root_model(self, x: int) -> str:
        """See ``pick_root_model`` and :meth:`pick_root_model`."""
        # then recommend_root_model runs; `pick_root_model()` returns
        if x:
            raise ValueError(f"pick_root_model: no candidates for {x}")
        raise ValueError("pick_root_model: no candidates")
'''

OTHER = '''\
from pkg.engine import SlayerQueryEngine


def f(e: SlayerQueryEngine) -> str:
    """Wraps :meth:`SlayerQueryEngine.recommend_root_model` and ``recommend_root_model``."""
    # calls recommend_root_model first
    getattr(e, "recommend_root_model")
    print("recommend_root_model")
    return e.recommend_root_model(1)
'''
OTHER_AFTER = '''\
from pkg.engine import SlayerQueryEngine


def f(e: SlayerQueryEngine) -> str:
    """Wraps :meth:`SlayerQueryEngine.pick_root_model` and ``recommend_root_model``."""
    # calls recommend_root_model first
    getattr(e, "pick_root_model")
    print("recommend_root_model")
    return e.pick_root_model(1)
'''

API_MD = (
    "# API\n\n"
    "Use `pkg.engine.SlayerQueryEngine.recommend_root_model` or `engine.SlayerQueryEngine.recommend_root_model`.\n"
    "Then recommend_root_model runs.\n"
)
NOTES_RST = "See :meth:`SlayerQueryEngine.recommend_root_model`.\n"
DATA_JSON = '{"call": "SlayerQueryEngine.recommend_root_model"}\n'


@pytest.fixture
def project(typed_project: MakeProject, monkeypatch: pytest.MonkeyPatch) -> MakeProject:
    """`typed_project` as a git repo (prose files come from git), entered as the working directory."""

    def make(files: dict[str, str], *, git: bool = True) -> Path:
        root = typed_project(files)
        if git:
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
        monkeypatch.chdir(root)
        return root

    return make


def _rename(root: Path, *flags: str, rel: str = "pkg/engine.py", needle: str = OLD, new_name: str = NEW) -> int:
    offset = (root / rel).read_text(encoding="utf-8").index(needle)
    return dr_refactor(["--project", str(root), "--apply", "rename", "--file", rel, "--offset", str(offset),
                        "--new-name", new_name, *flags])


def _read(root: Path, rel: str) -> str:
    return (root / rel).read_text(encoding="utf-8")


def _leftover(path: str, line: int, where: str, old: str = OLD) -> str:
    return message("refactor.leftover", path=path, line=line, where=where, old=old)


FILES = {
    "pkg/engine.py": ENGINE,
    "pkg/other.py": OTHER,
    "docs/api.md": API_MD,
    "docs/notes.rst": NOTES_RST,
    "docs/data.json": DATA_JSON,
}


def test_qualified_and_code_marked_mentions_are_rewritten(project: MakeProject) -> None:
    root = project(FILES)
    assert _rename(root, "--docs") == 0
    assert _read(root, "pkg/engine.py") == ENGINE_AFTER
    assert _read(root, "pkg/other.py") == OTHER_AFTER
    assert _read(root, "docs/api.md") == API_MD.replace(f"SlayerQueryEngine.{OLD}", f"SlayerQueryEngine.{NEW}")
    assert _read(root, "docs/notes.rst") == NOTES_RST.replace(OLD, NEW)
    assert _read(root, "docs/data.json") == DATA_JSON


def test_every_other_mention_is_listed_in_order(project: MakeProject, capsys: pytest.CaptureFixture[str]) -> None:
    root = project(FILES)
    assert _rename(root, "--docs") == 0
    assert capsys.readouterr().err.splitlines() == [
        _leftover("docs/api.md", 4, "prose"),
        _leftover("pkg/engine.py", 4, "comment"),
        _leftover("pkg/other.py", 5, "docstring"),
        _leftover("pkg/other.py", 6, "comment"),
        _leftover("pkg/other.py", 8, "string"),
    ]


def test_without_docs_nothing_is_scanned_or_listed(project: MakeProject, capsys: pytest.CaptureFixture[str]) -> None:
    root = project(FILES)
    assert _rename(root) == 0
    assert capsys.readouterr().err == ""
    assert _read(root, "pkg/engine.py") == ENGINE.replace(
        "    def recommend_root_model(", f"    def {NEW}("
    )
    assert _read(root, "pkg/other.py") == OTHER.replace('getattr(e, "recommend_root_model")', f'getattr(e, "{NEW}")'
                                                         ).replace(f"e.{OLD}(1)", f"e.{NEW}(1)")
    assert _read(root, "docs/api.md") == API_MD
    assert _read(root, "docs/notes.rst") == NOTES_RST


def test_a_simple_name_collision_is_listed(project: MakeProject, capsys: pytest.CaptureFixture[str]) -> None:
    legacy = 'class SlayerQueryEngine:\n    def recommend_root_model(self) -> str:\n        return ""\n'
    notes = (
        "# SlayerQueryEngine.recommend_root_model\n"
        "# engine.SlayerQueryEngine.recommend_root_model\n"
        "# legacy.SlayerQueryEngine.recommend_root_model\n"
    )
    root = project({"pkg/engine.py": ENGINE, "pkg/legacy.py": legacy, "pkg/notes.py": notes})
    assert _rename(root, "--docs", "--without", "pkg/legacy.py:2") == 0
    assert _read(root, "pkg/notes.py") == notes.replace(f"# engine.SlayerQueryEngine.{OLD}",
                                                         f"# engine.SlayerQueryEngine.{NEW}")
    err = capsys.readouterr().err.splitlines()
    assert _leftover("pkg/notes.py", 1, "comment") in err
    assert _leftover("pkg/notes.py", 3, "comment") in err
    assert _read(root, "pkg/legacy.py") == legacy


def test_git_ignored_prose_is_skipped(project: MakeProject, capsys: pytest.CaptureFixture[str]) -> None:
    mention = "See SlayerQueryEngine.recommend_root_model.\n"
    root = project({"pkg/engine.py": ENGINE, ".gitignore": "out/\n", "out/notes.md": mention})
    assert _rename(root, "--docs") == 0
    assert _read(root, "out/notes.md") == mention
    assert all("out/notes.md" not in line for line in capsys.readouterr().err.splitlines())


def test_no_prose_outside_git(project: MakeProject, capsys: pytest.CaptureFixture[str]) -> None:
    root = project({"pkg/engine.py": ENGINE, "docs/api.md": API_MD}, git=False)
    assert _rename(root, "--docs") == 0
    assert _read(root, "docs/api.md") == API_MD
    assert all("docs/api.md" not in line for line in capsys.readouterr().err.splitlines())


def test_module_level_symbol_qualified_by_its_module(project: MakeProject) -> None:
    util = "def helper() -> int:\n    return 1\n"
    use = "from pkg.util import helper\n\n# util.helper and pkg.util.helper, not other.helper\nx = helper()\n"
    root = project({"pkg/util.py": util, "pkg/use.py": use})
    assert _rename(root, "--docs", rel="pkg/util.py", needle="helper", new_name="assist") == 0
    assert _read(root, "pkg/use.py") == (
        "from pkg.util import assist\n\n# util.assist and pkg.util.assist, not other.helper\nx = assist()\n"
    )


def test_a_kept_prose_file_is_unchanged(project: MakeProject) -> None:
    root = project(FILES)
    assert _rename(root, "--docs", "--keep", "docs/api.md") == 0
    assert _read(root, "docs/api.md") == API_MD
    assert _read(root, "docs/notes.rst") == NOTES_RST.replace(OLD, NEW)
