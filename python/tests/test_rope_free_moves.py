"""Python moves start no language server and compute nothing with rope; only the walker-gap check still uses it."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from project_files import file_tree, write_project
from refactor_cli import run, run_raw
from rope.base import libutils
from rope.base.change import ChangeSet
from rope.base.project import Project
from rope.refactor import move as rope_move
from rope.refactor import occurrences
from rope.refactor.move import MoveGlobal, MoveMethod, MoveModule

from living_architecture.contract import message
from living_architecture.refactor import writer

FILES = {
    "pkg/sql/__init__.py": "",
    "pkg/sql/client.py": "X = 1\n",
    "pkg/database/__init__.py": "",
    "pkg/a.py": "import os\n\n\ndef f() -> str:\n    return os.sep\n\n\ndef g() -> str:\n    return f()\n",
    "pkg/b.py": '"""B."""\n',
    "use.py": "from pkg.a import f\nfrom pkg.sql import client\n\nprint(f(), client.X)\n",
}
SYMBOL_ARGV = ["move-symbol", "--file", "pkg/a.py", "--symbol", "f", "--dest", "pkg/b.py"]
MODULE_ARGV = ["move-module", "--module", "pkg/sql/client.py", "--dest", "pkg/database"]
SYMBOL_OUT = """Moving global <f>:


--- a/pkg/a.py
+++ b/pkg/a.py
@@ -1,8 +1,4 @@
-import os
-
-
-def f() -> str:
-    return os.sep
+from pkg.b import f
\x20
\x20
 def g() -> str:

--- a/pkg/b.py
+++ b/pkg/b.py
@@ -1 +1,6 @@
 \"\"\"B.\"\"\"
+import os
+
+
+def f() -> str:
+    return os.sep

--- a/use.py
+++ b/use.py
@@ -1,4 +1,4 @@
-from pkg.a import f
+from pkg.b import f
 from pkg.sql import client
\x20
 print(f(), client.X)



DRY-RUN. 3 file(s) would change. Re-run with --apply.
"""
MODULE_OUT = """Moving module <client>:


rename from pkg/sql/client.py
rename to pkg/database/client.py
--- a/use.py
+++ b/use.py
@@ -1,4 +1,4 @@
 from pkg.a import f
-from pkg.sql import client
+from pkg.database import client
\x20
 print(f(), client.X)



DRY-RUN. 2 file(s) would change. Re-run with --apply.
"""


def _refuse(what: str) -> object:
    def refuse(*_: object, **__: object) -> None:
        raise AssertionError(f"a move used {what}")

    return refuse


@pytest.fixture
def no_rope(monkeypatch: pytest.MonkeyPatch) -> None:
    for cls in (Project, ChangeSet, MoveGlobal, MoveModule, MoveMethod, occurrences.Finder):
        monkeypatch.setattr(cls, "__init__", _refuse(cls.__name__))
    monkeypatch.setattr(MoveGlobal, "_get_moving_region", _refuse("rope's moving region"))
    monkeypatch.setattr(MoveGlobal, "_get_moving_element_with_imports", _refuse("rope's moved imports"))
    monkeypatch.setattr(occurrences, "create_finder", _refuse("rope's finder"))
    monkeypatch.setattr(rope_move, "create_move", _refuse("rope's create_move"))
    monkeypatch.setattr(libutils, "modname", _refuse("rope's modname"))


@pytest.mark.usefixtures("no_rope")
@pytest.mark.parametrize(("argv", "out"), [(SYMBOL_ARGV, SYMBOL_OUT), (MODULE_ARGV, MODULE_OUT)],
                         ids=["move-symbol", "move-module"])
def test_a_move_computes_nothing_with_rope(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                          capsys: pytest.CaptureFixture[str], argv: list[str], out: str) -> None:
    root = write_project(tmp_path / "proj", FILES)
    assert run(root, argv, monkeypatch, capsys) == (0, out, "")


@pytest.mark.usefixtures("no_rope")
def test_the_walker_gap_check_still_runs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                         capsys: pytest.CaptureFixture[str],
                                         restore_rope_visitor: Callable[[str], None], annotation_gap: str) -> None:
    restore_rope_visitor("_arg")
    root = write_project(tmp_path / "proj", {**FILES, "gap.py": annotation_gap})
    code, out, err = run(root, SYMBOL_ARGV, monkeypatch, capsys)
    assert (code, out) == (1, "")
    assert message("refactor.rope-walk", path="gap.py", line=3) in err


@pytest.mark.usefixtures("no_rope")
def test_a_package_moved_by_its_init_checks_walker_gaps_under_its_own_name(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
        restore_rope_visitor: Callable[[str], None], annotation_gap: str) -> None:
    restore_rope_visitor("_arg")
    root = write_project(tmp_path / "proj", {**FILES, "gap.py": annotation_gap + "# sql\n"})
    argv = ["move-module", "--module", "pkg/sql/__init__.py", "--dest", "pkg/database"]
    code, out, err = run(root, argv, monkeypatch, capsys)
    assert (code, out) == (1, "")
    assert message("refactor.rope-walk", path="gap.py", line=3) in err


@pytest.mark.usefixtures("no_server")
@pytest.mark.parametrize("flags", [[], ["--apply"]], ids=["dry-run", "apply"])
@pytest.mark.parametrize("argv", [SYMBOL_ARGV, MODULE_ARGV], ids=["move-symbol", "move-module"])
def test_a_move_starts_no_language_server(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                          capsys: pytest.CaptureFixture[str], flags: list[str], argv: list[str]) -> None:
    root = write_project(tmp_path / "proj", FILES)
    code, _out, err = run(root, [*flags, *argv], monkeypatch, capsys)
    assert (code, err) == (0, "")


@pytest.mark.parametrize(
    ("files", "argv", "touched"),
    [
        ({**FILES, "ref.py": "import pkg.sql.client\n\nprint(pkg.sql.client.X)\n"}, MODULE_ARGV, "ref.py"),
        ({**FILES, "pkg/sql/dialects.py": "from pkg.sql import client\n\nD = client.X\n"},
         ["move-module", "--module", "pkg/sql", "--dest", "pkg/database"], "pkg/sql/dialects.py"),
        (FILES, ["move-module", "--module", "pkg/sql", "--dest", "pkg/database"], "pkg/sql/client.py"),
    ],
    ids=["reference-only-file", "child-of-a-moved-package", "unedited-moved-file"],
)
def test_a_file_changed_between_read_and_write_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
    files: dict[str, str], argv: list[str], touched: str,
) -> None:
    root = write_project(tmp_path / "proj", files)
    original = writer.verify

    def touching(at: Path, writes: list[writer.FileWrite]) -> None:
        (root / touched).write_text((root / touched).read_text(encoding="utf-8") + "# edited\n", encoding="utf-8")
        original(at, writes)

    monkeypatch.setattr(writer, "verify", touching)
    before = file_tree(root)
    code, _out, err = run_raw(root, ["--apply", *argv], monkeypatch, capsys)
    assert code == 1
    assert err.endswith(message("refactor.file-changed", path=touched) + "\n")
    assert file_tree(root) == {**before, touched: before[touched] + b"# edited\n"}
