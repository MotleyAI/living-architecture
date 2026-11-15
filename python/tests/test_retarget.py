"""Python `dr-refactor retarget`: references to an alias are rewritten to name its target; the alias stays."""

from __future__ import annotations

from pathlib import Path

import pytest
from project_files import file_tree, write_project
from refactor_cli import read, run

from living_architecture.contract import message

ENGINE = """\
class Engine:
    def save_model(self, m: int) -> None:
        print(m)

    def save(self, m: int) -> None:
        return self.save_model(m)
"""
ENGINE_USE = "from pkg.engine import Engine\n\n\ndef use(engine: Engine) -> None:\n    engine.save(1)\n"


def _retarget(rel: str, symbol: str, target: str, *flags: str, apply: bool = True) -> list[str]:
    return [*(["--apply"] if apply else []), "retarget", "--file", rel, "--symbol", symbol, "--target", target, *flags]


def test_method_twin(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    root = write_project(tmp_path / "proj", {"pkg/engine.py": ENGINE, "pkg/use.py": ENGINE_USE})
    code, out, err = run(root, _retarget("pkg/engine.py", "Engine.save", "Engine.save_model"), monkeypatch, capsys)
    assert (code, err) == (0, "")
    assert out.splitlines()[0] == message("refactor.retarget-header", old="save", new="save_model")
    assert read(root, "pkg/engine.py") == ENGINE
    assert read(root, "pkg/use.py") == ENGINE_USE.replace("engine.save(1)", "engine.save_model(1)")


def test_dry_run_writes_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    root = write_project(tmp_path / "proj", {"pkg/engine.py": ENGINE, "pkg/use.py": ENGINE_USE})
    before = file_tree(root)
    code, out, _err = run(root, _retarget("pkg/engine.py", "Engine.save", "Engine.save_model", apply=False),
                          monkeypatch, capsys)
    assert code == 0
    assert "+    engine.save_model(1)\n" in out
    assert message("refactor.dry-run", count=1) in out
    assert file_tree(root) == before


MODELS = "class Model:\n    pass\n\n\nAcmeModel = Model\n"


def test_class_twin_and_its_imports(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = write_project(tmp_path / "proj", {
        "pkg/models.py": MODELS,
        "pkg/both.py": "from pkg.models import Model, AcmeModel\n\n\ndef make() -> Model:\n    return AcmeModel()\n",
        "pkg/only.py": "from pkg.models import AcmeModel\n\n\ndef make() -> object:\n    return AcmeModel()\n",
    })
    code, _out, err = run(root, _retarget("pkg/models.py", "AcmeModel", "Model"), monkeypatch, capsys)
    assert (code, err) == (0, "")
    assert read(root, "pkg/models.py") == MODELS
    assert read(root, "pkg/both.py") == "from pkg.models import Model\n\n\ndef make() -> Model:\n    return Model()\n"
    assert read(root, "pkg/only.py") == "from pkg.models import Model\n\n\ndef make() -> object:\n    return Model()\n"


def test_a_reexport_shim_is_kept(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    shim = 'from pkg.models import Model, AcmeModel\n\n__all__ = ["Model", "AcmeModel"]\n'
    models = MODELS + '\n__all__ = ["Model", "AcmeModel"]\n'
    root = write_project(tmp_path / "proj", {
        "pkg/models.py": models,
        "pkg/compat.py": shim,
        "pkg/only.py": "from pkg.compat import AcmeModel\n\n\ndef make() -> object:\n    return AcmeModel()\n",
    })
    code, _out, err = run(root, _retarget("pkg/models.py", "AcmeModel", "Model"), monkeypatch, capsys)
    assert (code, err) == (0, "")
    assert [read(root, "pkg/models.py"), read(root, "pkg/compat.py")] == [models, shim]
    assert read(root, "pkg/only.py") == "from pkg.compat import Model\n\n\ndef make() -> object:\n    return Model()\n"


def test_a_single_name_shim_and_its_importers_are_kept(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    shim = 'from pkg.models import AcmeModel\n\n__all__ = ["AcmeModel"]\n\n\ndef make() -> object:\n    return AcmeModel()\n'
    use = "from pkg.compat import AcmeModel\n\na = AcmeModel()\n"
    root = write_project(tmp_path / "proj", {
        "pkg/models.py": MODELS,
        "pkg/compat.py": shim,
        "pkg/use.py": use,
        "pkg/direct.py": "from pkg.models import AcmeModel\n\nb = AcmeModel()\n",
    })
    code, _out, err = run(root, _retarget("pkg/models.py", "AcmeModel", "Model"), monkeypatch, capsys)
    assert (code, err) == (0, "")
    assert [read(root, "pkg/compat.py"), read(root, "pkg/use.py")] == [shim, use]
    assert read(root, "pkg/direct.py") == "from pkg.models import Model\n\nb = Model()\n"


def test_import_alias_keeps_its_local_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = write_project(tmp_path / "proj", {
        "pkg/models.py": MODELS,
        "pkg/aliased.py": "from pkg.models import AcmeModel as SM\n\n\ndef make() -> object:\n    return SM()\n",
    })
    code, _out, err = run(root, _retarget("pkg/models.py", "AcmeModel", "Model"), monkeypatch, capsys)
    assert (code, err) == (0, "")
    assert read(root, "pkg/aliased.py") == "from pkg.models import Model as SM\n\n\ndef make() -> object:\n    return SM()\n"


def test_other_scope_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    root = write_project(tmp_path / "proj", {
        "pkg/core.py": "class Model:\n    pass\n",
        "pkg/compat.py": "from pkg.core import Model\n\nAcmeModel = Model\n",
        "pkg/use.py": "from pkg.compat import AcmeModel\n\nX = AcmeModel()\n",
    })
    before = file_tree(root)
    expected = message("refactor.retarget-scope", target="Model", alias="AcmeModel")
    assert run(root, _retarget("pkg/compat.py", "AcmeModel", "Model"), monkeypatch, capsys) == (2, "", f"{expected}\n")
    assert file_tree(root) == before


def test_overridden_alias_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    root = write_project(tmp_path / "proj", {
        "pkg/engine.py": ENGINE,
        "pkg/use.py": ENGINE_USE,
        "pkg/fast.py": "from pkg.engine import Engine\n\n\nclass FastEngine(Engine):\n    def save(self, m: int) -> None:\n"
                       "        print('fast', m)\n",
    })
    before = file_tree(root)
    expected = message("refactor.retarget-override", path="pkg/fast.py", line=5, cls="FastEngine", name="save")
    assert run(root, _retarget("pkg/engine.py", "Engine.save", "Engine.save_model"), monkeypatch, capsys) == (
        1, "", f"{expected}\n")
    assert file_tree(root) == before


def test_shadowed_target_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    root = write_project(tmp_path / "proj", {
        "pkg/models.py": MODELS,
        "pkg/use.py": "from pkg.models import AcmeModel\n\n\ndef make() -> object:\n    Model = 3\n"
                      "    return AcmeModel(), Model\n",
    })
    before = file_tree(root)
    expected = message("refactor.retarget-shadowed", path="pkg/use.py", line=6, name="Model")
    assert run(root, _retarget("pkg/models.py", "AcmeModel", "Model"), monkeypatch, capsys) == (1, "", f"{expected}\n")
    assert file_tree(root) == before


ACCESSOR = """\
class C:
    def __init__(self) -> None:
        self.value = 1

    @property
    def old(self) -> int:
        return self.value


def read(c: C) -> int:
    return c.old + c.value
"""


def test_property_alias(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    root = write_project(tmp_path / "proj", {"pkg/c.py": ACCESSOR})
    code, _out, err = run(root, _retarget("pkg/c.py", "C.old", "C.value"), monkeypatch, capsys)
    assert (code, err) == (0, "")
    assert read(root, "pkg/c.py") == ACCESSOR.replace("return c.old + c.value", "return c.value + c.value")


def test_name_already_in_use_is_not_a_conflict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = write_project(tmp_path / "proj", {
        "pkg/models.py": MODELS + "\n\ndef build() -> Model:\n    return AcmeModel()\n",
    })
    code, _out, err = run(root, _retarget("pkg/models.py", "AcmeModel", "Model"), monkeypatch, capsys)
    assert (code, err) == (0, "")
    assert read(root, "pkg/models.py") == MODELS + "\n\ndef build() -> Model:\n    return Model()\n"


def test_a_source_in_an_excluded_directory_is_not_rewritten(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    vendored = "from pkg.models import AcmeModel\n\nX = AcmeModel()\n"
    root = write_project(tmp_path / "proj", {"pkg/models.py": MODELS, "venv/lib/use.py": vendored})
    code, _out, err = run(root, _retarget("pkg/models.py", "AcmeModel", "Model"), monkeypatch, capsys)
    assert (code, err) == (0, "")
    assert read(root, "venv/lib/use.py") == vendored


@pytest.mark.parametrize(("line", "kept"), [
    ("from pkg.models import AcmeModel; value = 1\n", "value = 1\n"),
    ("value = 1; from pkg.models import AcmeModel\n", "value = 1\n"),
    ("from pkg.models import AcmeModel  # legacy\n", ""),
], ids=["first", "last", "alone"])
def test_a_duplicate_import_is_removed_without_its_neighbours(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], line: str, kept: str
) -> None:
    use = f"from pkg.models import Model\n{line}\n\ndef make() -> Model:\n    return AcmeModel()\n"
    root = write_project(tmp_path / "proj", {"pkg/models.py": MODELS, "pkg/use.py": use})
    code, _out, err = run(root, _retarget("pkg/models.py", "AcmeModel", "Model"), monkeypatch, capsys)
    assert (code, err) == (0, "")
    assert read(root, "pkg/use.py") == f"from pkg.models import Model\n{kept}\n\ndef make() -> Model:\n    return Model()\n"


def test_a_local_import_of_the_target_is_no_shadow(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    use = "def make() -> object:\n    from pkg.models import Model, AcmeModel\n    return AcmeModel()\n"
    root = write_project(tmp_path / "proj", {"pkg/models.py": MODELS, "pkg/use.py": use})
    code, _out, err = run(root, _retarget("pkg/models.py", "AcmeModel", "Model"), monkeypatch, capsys)
    assert (code, err) == (0, "")
    assert read(root, "pkg/use.py") == "def make() -> object:\n    from pkg.models import Model\n    return Model()\n"


@pytest.mark.parametrize(
    ("use", "expected"),
    [
        ("from pkg.models import AcmeModel\nimport pkg.other\nfrom pkg.models import Model\n\na = AcmeModel()\nb = Model()\n",
         "from pkg.models import Model\nimport pkg.other\n\na = Model()\nb = Model()\n"),
        ("from pkg.models import Model\nimport pkg.other\nfrom pkg.models import AcmeModel\n\na = AcmeModel()\nb = Model()\n",
         "from pkg.models import Model\nimport pkg.other\n\na = Model()\nb = Model()\n"),
    ],
    ids=["alias first", "target first"],
)
def test_of_two_imports_of_the_module_the_later_is_removed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], use: str, expected: str
) -> None:
    root = write_project(tmp_path / "proj", {"pkg/models.py": MODELS, "pkg/other.py": "", "pkg/use.py": use})
    code, _out, err = run(root, _retarget("pkg/models.py", "AcmeModel", "Model"), monkeypatch, capsys)
    assert (code, err) == (0, "")
    assert read(root, "pkg/use.py") == expected


def test_a_local_import_of_the_alias_before_one_of_the_target_is_rewritten_in_place(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    use = ("def build() -> object:\n    from pkg.models import AcmeModel\n    value = AcmeModel()\n"
           "    from pkg.models import Model\n    return value\n")
    root = write_project(tmp_path / "proj", {"pkg/models.py": MODELS, "pkg/use.py": use})
    code, _out, err = run(root, _retarget("pkg/models.py", "AcmeModel", "Model"), monkeypatch, capsys)
    assert (code, err) == (0, "")
    assert read(root, "pkg/use.py") == "def build() -> object:\n    from pkg.models import Model\n    value = Model()\n    return value\n"


def test_a_local_import_of_the_target_after_the_use_shadows_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    use = ("from pkg.models import AcmeModel\n\n\ndef build() -> object:\n    value = AcmeModel()\n"
           "    from pkg.models import Model\n    return value\n")
    root = write_project(tmp_path / "proj", {"pkg/models.py": MODELS, "pkg/use.py": use})
    before = file_tree(root)
    code, out, err = run(root, _retarget("pkg/models.py", "AcmeModel", "Model"), monkeypatch, capsys)
    shadowed = message("refactor.retarget-shadowed", path="pkg/use.py", line=5, name="Model")
    assert (code, out, err) == (1, "", f"{shadowed}\n")
    assert file_tree(root) == before


def test_a_target_imported_before_the_use_in_its_branch_is_no_shadow(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    use = ("from pkg.models import AcmeModel\n\n\ndef build(flag: bool) -> object:\n    if flag:\n"
           "        from pkg.models import Model\n        value = AcmeModel()\n        return value\n    return None\n")
    root = write_project(tmp_path / "proj", {"pkg/models.py": MODELS, "pkg/use.py": use})
    code, _out, err = run(root, _retarget("pkg/models.py", "AcmeModel", "Model"), monkeypatch, capsys)
    assert (code, err) == (0, "")
    assert "        value = Model()\n" in read(root, "pkg/use.py")


def test_a_target_imported_in_a_branch_before_a_use_outside_it_shadows_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    use = ("from pkg.models import AcmeModel\n\n\ndef build(flag: bool) -> object:\n    if flag:\n"
           "        from pkg.models import Model\n    return AcmeModel()\n")
    root = write_project(tmp_path / "proj", {"pkg/models.py": MODELS, "pkg/use.py": use})
    before = file_tree(root)
    code, out, err = run(root, _retarget("pkg/models.py", "AcmeModel", "Model"), monkeypatch, capsys)
    shadowed = message("refactor.retarget-shadowed", path="pkg/use.py", line=7, name="Model")
    assert (code, out, err) == (1, "", f"{shadowed}\n")
    assert file_tree(root) == before


def test_an_import_in_another_branch_is_no_duplicate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    use = ("import sys\n\nif sys.version_info >= (3, 11):\n    from pkg.models import Model\nelse:\n"
           "    from pkg.models import AcmeModel\nuse = AcmeModel\n")
    root = write_project(tmp_path / "proj", {"pkg/models.py": MODELS, "pkg/use.py": use})
    code, _out, err = run(root, _retarget("pkg/models.py", "AcmeModel", "Model"), monkeypatch, capsys)
    assert (code, err) == (0, "")
    assert read(root, "pkg/use.py") == use.replace("import AcmeModel\n", "import Model\n").replace("= AcmeModel", "= Model")
