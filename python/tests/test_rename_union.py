"""Python `dr-refactor rename`: rope's edits plus every reference basedpyright resolves."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from project_files import file_tree

from living_architecture.cli import dr_refactor
from living_architecture.contract import message
from living_architecture.lang import LanguageServer, LanguageServerError, Span

MakeProject = Callable[..., Path]
BROKEN_NODE = "--require /nonexistent.js"

FORWARD_REFS = (
    "from typing import Optional\n\n\n"
    "class Rec:\n    pass\n\n\n"
    'def make() -> "Rec":\n    return Rec()\n\n\n'
    'def opt(a: Optional["Rec"], b: list["Rec"], c: "Rec | None") -> None: ...\n'
)
FORWARD_USE = 'from pkg.models import Rec\n\n\ndef f() -> "Rec | None":\n    return None\n'

RECEIVERS_A = "class A:\n    def get_model(self) -> int:\n        return 1\n"
RECEIVERS_USE = (
    "from pkg.a import A\n\n\n"
    "def make() -> A:\n    return A()\n\n\n"
    "class Holder:\n    store: A\n\n"
    "    def __init__(self, s: A) -> None:\n        self.s: A = s\n\n"
    "    def run(self) -> int:\n        return self.s.get_model() + self.store.get_model()\n\n\n"
    "def calls(a: A, o: object) -> int:\n"
    "    x = A()\n"
    "    total = a.get_model() + make().get_model() + x.get_model()\n"
    "    if isinstance(o, A):\n        total += o.get_model()\n"
    "    return total\n"
)

HIERARCHY = (
    "class A:\n    def run(self) -> int:\n        return 1\n\n\n"
    "class B(A):\n    def run(self) -> int:\n        return super().run() + 1\n\n\n"
    "def calls(a: A, b: B) -> int:\n    return a.run() + b.run()\n"
)


def _rename(root: Path, rel: str, new_name: str, *locator: str, apply: bool = True) -> int:
    flags = ["--apply"] if apply else []
    return dr_refactor(["--project", str(root), *flags, "rename", "--file", str(root / rel), *locator,
                        "--new-name", new_name])


def _at(root: Path, rel: str, needle: str) -> tuple[str, str]:
    return "--offset", str((root / rel).read_text(encoding="utf-8").index(needle))


def _read(root: Path, rel: str) -> str:
    return (root / rel).read_text(encoding="utf-8")


def test_forward_reference_strings_follow_the_class(typed_project: MakeProject) -> None:
    root = typed_project({"pkg/models.py": FORWARD_REFS, "pkg/use.py": FORWARD_USE})
    assert _rename(root, "pkg/models.py", "Recommendation", "--name", "Rec") == 0
    assert _read(root, "pkg/models.py") == FORWARD_REFS.replace("Rec", "Recommendation")
    assert _read(root, "pkg/use.py") == FORWARD_USE.replace("Rec", "Recommendation")


def test_pydantic_field_keyword_arguments_follow_the_field(typed_project: MakeProject) -> None:
    models = (
        "from pydantic import BaseModel\n\n\n"
        "class Model(BaseModel):\n    columns: list[int] = []\n\n\n"
        "class Sub(Model):\n    extra: int = 0\n"
    )
    use = (
        "from pkg.models import Model, Sub\n\n\n"
        "def build(kind: type[Model]) -> list[Model]:\n"
        "    return [Model(columns=[]), Sub(columns=[], extra=1), kind(columns=[])]\n"
    )
    root = typed_project({"pkg/models.py": models, "pkg/use.py": use})
    assert _rename(root, "pkg/models.py", "fields", *_at(root, "pkg/models.py", "columns")) == 0
    assert _read(root, "pkg/models.py") == models.replace("columns", "fields")
    assert _read(root, "pkg/use.py") == use.replace("columns", "fields")


def test_dataclass_field_keyword_arguments(typed_project: MakeProject) -> None:
    models = "from dataclasses import dataclass\n\n\n@dataclass\nclass D:\n    size: int\n"
    use = "from pkg.models import D\n\nd = D(size=1)\n"
    root = typed_project({"pkg/models.py": models, "pkg/use.py": use})
    assert _rename(root, "pkg/models.py", "width", *_at(root, "pkg/models.py", "size")) == 0
    assert _read(root, "pkg/use.py") == use.replace("size", "width")


def test_annotated_and_inferred_receivers(typed_project: MakeProject) -> None:
    root = typed_project({"pkg/a.py": RECEIVERS_A, "pkg/use.py": RECEIVERS_USE})
    assert _rename(root, "pkg/a.py", "get_dataset", *_at(root, "pkg/a.py", "get_model")) == 0
    assert _read(root, "pkg/a.py") == RECEIVERS_A.replace("get_model", "get_dataset")
    assert _read(root, "pkg/use.py") == RECEIVERS_USE.replace("get_model", "get_dataset")


def test_super_call_in_an_override(typed_project: MakeProject) -> None:
    source = (
        "class A:\n    def sync_model(self, x: int) -> int:\n        return x\n\n\n"
        "class B(A):\n    def sync_model(self, x: int) -> int:\n        return super().sync_model(x)\n"
    )
    root = typed_project({"pkg/a.py": source})
    assert _rename(root, "pkg/a.py", "sync_dataset", *_at(root, "pkg/a.py", "sync_model")) == 0
    assert _read(root, "pkg/a.py") == source.replace("sync_model", "sync_dataset")


def test_hierarchy_renamed_by_default(typed_project: MakeProject) -> None:
    root = typed_project({"pkg/a.py": HIERARCHY})
    assert _rename(root, "pkg/a.py", "execute", *_at(root, "pkg/a.py", "run")) == 0
    assert _read(root, "pkg/a.py") == HIERARCHY.replace("run", "execute")


def test_no_in_hierarchy_renames_only_the_located_declaration(typed_project: MakeProject) -> None:
    root = typed_project({"pkg/a.py": HIERARCHY})
    assert _rename(root, "pkg/a.py", "execute", *_at(root, "pkg/a.py", "run"), "--no-in-hierarchy") == 0
    assert _read(root, "pkg/a.py") == (
        "class A:\n    def execute(self) -> int:\n        return 1\n\n\n"
        "class B(A):\n    def run(self) -> int:\n        return super().execute() + 1\n\n\n"
        "def calls(a: A, b: B) -> int:\n    return a.execute() + b.run()\n"
    )


def test_positions_after_astral_characters_and_crlf(typed_project: MakeProject) -> None:
    source = (
        "class Rec:\r\n    pass\r\n\r\n\r\n"
        "def make() -> Rec:\r\n    return Rec()\r\n\r\n\r\n"
        's = "😀é"; r: "Rec" = make()'
    )
    root = typed_project({"pkg/models.py": source})
    assert _rename(root, "pkg/models.py", "Recommendation", "--name", "Rec") == 0
    assert (root / "pkg" / "models.py").read_bytes() == source.replace("Rec", "Recommendation").encode()


@pytest.mark.parametrize("apply", [False, True], ids=["dry-run", "apply"])
def test_language_server_that_cannot_start(
    typed_project: MakeProject, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], apply: bool
) -> None:
    root = typed_project({"pkg/models.py": FORWARD_REFS})
    before = file_tree(root)
    monkeypatch.setenv("NODE_OPTIONS", BROKEN_NODE)
    assert _rename(root, "pkg/models.py", "Recommendation", "--name", "Rec", apply=apply) == 1
    assert capsys.readouterr() == ("", message("refactor.pyright-failed") + "\n")
    assert file_tree(root) == before


@pytest.mark.parametrize("apply", [False, True], ids=["dry-run", "apply"])
def test_language_server_failing_after_rope_computed_its_changes(
    typed_project: MakeProject, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], apply: bool
) -> None:
    def fail(*_: object, **__: object) -> None:
        raise LanguageServerError("exited")

    root = typed_project({"pkg/models.py": FORWARD_REFS})
    before = file_tree(root)
    monkeypatch.setattr(LanguageServer, "references", fail)
    assert _rename(root, "pkg/models.py", "Recommendation", "--name", "Rec", apply=apply) == 1
    assert capsys.readouterr() == ("", message("refactor.pyright-failed") + "\n")
    assert file_tree(root) == before


def test_a_file_changed_before_the_write_aborts_with_nothing_written(
    typed_project: MakeProject, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = typed_project({"pkg/models.py": FORWARD_REFS, "pkg/use.py": FORWARD_USE})
    original = LanguageServer.references

    def touching(self: LanguageServer, path: Path, offset: int) -> list[Span]:
        use = root / "pkg" / "use.py"
        if not use.read_text(encoding="utf-8").endswith("# edited\n"):
            use.write_text(use.read_text(encoding="utf-8") + "# edited\n", encoding="utf-8")
        return original(self, path, offset)

    monkeypatch.setattr(LanguageServer, "references", touching)
    assert _rename(root, "pkg/models.py", "Recommendation", "--name", "Rec") == 1
    assert capsys.readouterr() == ("", message("refactor.file-changed", path="pkg/use.py") + "\n")
    assert _read(root, "pkg/models.py") == FORWARD_REFS
    assert _read(root, "pkg/use.py") == FORWARD_USE + "# edited\n"


def test_no_target_repo_code_runs(
    typed_project: MakeProject, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    marker = tmp_path / "MARKER"
    root = typed_project({
        "sitecustomize.py": f"import pathlib\npathlib.Path({str(marker)!r}).write_text('ran')\n",
        "pkg/models.py": FORWARD_REFS,
    }, venv=False)
    monkeypatch.chdir(root)
    assert _rename(root, "pkg/models.py", "Recommendation", "--name", "Rec") == 0
    assert not marker.exists()


def test_dry_run_leaves_the_tree_unchanged(typed_project: MakeProject, capsys: pytest.CaptureFixture[str]) -> None:
    root = typed_project({"pkg/models.py": FORWARD_REFS, "pkg/use.py": FORWARD_USE})
    before = file_tree(root)
    assert _rename(root, "pkg/models.py", "Recommendation", "--name", "Rec", apply=False) == 0
    out = capsys.readouterr().out.splitlines()
    assert '+def make() -> "Recommendation":' in out
    assert '+def f() -> "Recommendation | None":' in out
    assert file_tree(root) == before


def test_one_language_server_session_per_command(typed_project: MakeProject, monkeypatch: pytest.MonkeyPatch) -> None:
    starts: list[None] = []
    original = LanguageServer.__enter__

    def counting(self: LanguageServer) -> LanguageServer:
        starts.append(None)
        return original(self)

    monkeypatch.setattr(LanguageServer, "__enter__", counting)
    root = typed_project({"pkg/a.py": HIERARCHY, "pkg/use.py": "from pkg.a import A\n\n\ndef g(a: A) -> int:\n    return a.run()\n"})
    assert _rename(root, "pkg/a.py", "execute", *_at(root, "pkg/a.py", "run")) == 0
    assert len(starts) == 1


def test_module_rename_keeps_ropes_behaviour_alone(typed_project: MakeProject, monkeypatch: pytest.MonkeyPatch) -> None:
    use = "from pkg import client\n\n\ndef g() -> int:\n    return client.run()\n"
    root = typed_project({"pkg/client.py": "def run() -> int:\n    return 1\n", "pkg/use.py": use})
    monkeypatch.setenv("NODE_OPTIONS", BROKEN_NODE)
    assert _rename(root, "pkg/use.py", "cli2", "--name", "client") == 0
    assert (root / "pkg" / "cli2.py").is_file()
    assert _read(root, "pkg/use.py") == use.replace("client", "cli2")
