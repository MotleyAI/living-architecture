"""Python `dr-refactor retarget`: references to an alias are rewritten to name its target; the alias stays."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
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


def test_a_single_name_shim_and_its_importers_are_rewritten(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    shim = 'from pkg.models import AcmeModel\n\n__all__ = ["AcmeModel"]\n\n\ndef make() -> object:\n    return AcmeModel()\n'
    root = write_project(tmp_path / "proj", {
        "pkg/models.py": MODELS,
        "pkg/compat.py": shim,
        "pkg/use.py": "from pkg.compat import AcmeModel\n\na = AcmeModel()\n",
        "pkg/direct.py": "from pkg.models import AcmeModel\n\nb = AcmeModel()\n",
    })
    code, _out, err = run(root, _retarget("pkg/models.py", "AcmeModel", "Model"), monkeypatch, capsys)
    assert (code, err) == (0, "")
    assert read(root, "pkg/compat.py") == shim.replace(
        "import AcmeModel\n", "import AcmeModel\nfrom pkg.models import Model\n").replace("return AcmeModel()", "return Model()")
    assert read(root, "pkg/use.py") == "from pkg.models import Model\n\na = Model()\n"
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


def test_a_target_imported_from_another_module_is_accepted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    compat = "from pkg.core import Model\n\nAcmeModel = Model\n"
    root = write_project(tmp_path / "proj", {
        "pkg/core.py": "class Model:\n    pass\n",
        "pkg/compat.py": compat,
        "pkg/use.py": "from pkg.compat import AcmeModel\n\nX = AcmeModel()\n",
    })
    code, _out, err = run(root, _retarget("pkg/compat.py", "AcmeModel", "Model"), monkeypatch, capsys)
    assert (code, err) == (0, "")
    assert read(root, "pkg/compat.py") == compat
    assert read(root, "pkg/use.py") == "from pkg.core import Model\n\nX = Model()\n"


def test_a_member_alias_with_a_target_in_another_class_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    store = "class Store:\n    def save_model(self, m: int) -> None:\n        print(m)\n\n\n"
    root = write_project(tmp_path / "proj", {"pkg/engine.py": store + ENGINE, "pkg/use.py": ENGINE_USE})
    before = file_tree(root)
    expected = message("refactor.retarget-scope", target="Store.save_model", alias="Engine.save")
    assert run(root, _retarget("pkg/engine.py", "Engine.save", "Store.save_model"), monkeypatch, capsys) == (
        2, "", f"{expected}\n")
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


def test_a_target_named_like_a_builtin_is_shadowed_where_the_builtin_is_in_scope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = write_project(tmp_path / "proj", {
        "pkg/home.py": "def len(x: str) -> int:\n    return 99\n\n\nold = len\n",
        "pkg/use.py": 'from pkg.home import old\n\noriginal = len("abc")\nvalue = old("abc")\n',
    })
    before = file_tree(root)
    code, out, err = run(root, _retarget("pkg/home.py", "old", "len"), monkeypatch, capsys)
    shadowed = message("refactor.retarget-shadowed", path="pkg/use.py", line=4, name="len")
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


CORE = "class Model:\n    pass\n\n\nclass Part:\n    pass\n\n\ndef helper() -> int:\n    return 1\n"
COMPAT = "from pkg.core import Model, Part\n\nCONST = 1\nAcmeModel = Model\nAcmePart = Part\n"


def _imported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], files: dict[str, str],
    alias: str = "AcmeModel", target: str = "Model",
) -> Path:
    """Retarget `alias` of `pkg/compat.py`, whose target is imported from `pkg.core` unless `files` say otherwise."""
    root = write_project(tmp_path / "proj", {"pkg/core.py": CORE, "pkg/compat.py": COMPAT, **files})
    code, _out, err = run(root, _retarget("pkg/compat.py", alias, target), monkeypatch, capsys)
    assert (code, err) == (0, "")
    return root


@pytest.mark.parametrize(("use", "expected"), [
    ("from pkg.core import helper\nfrom pkg.compat import CONST, AcmeModel\n\nx = CONST, AcmeModel(), helper()\n",
     "from pkg.core import helper, Model\nfrom pkg.compat import CONST\n\nx = CONST, Model(), helper()\n"),
    ("from pkg.compat import AcmeModel\n\nx = AcmeModel()\n", "from pkg.core import Model\n\nx = Model()\n"),
    ("from pkg.compat import CONST, AcmeModel\n\nx = CONST, AcmeModel()\n",
     "from pkg.compat import CONST\nfrom pkg.core import Model\n\nx = CONST, Model()\n"),
    ("from pkg.compat import AcmeModel as Z\n\nx = Z()\n", "from pkg.core import Model as Z\n\nx = Z()\n"),
    ("from pkg.compat import CONST, AcmeModel as Z\n\nx = CONST, Z()\n",
     "from pkg.compat import CONST\nfrom pkg.core import Model as Z\n\nx = CONST, Z()\n"),
    ("from pkg.compat import (  # legacy\n    AcmeModel,  # the alias\n)\n\nx = AcmeModel()\n",
     "from pkg.core import (  # legacy\n    Model,  # the alias\n)\n\nx = Model()\n"),
], ids=["joins an earlier home import", "replaces a sole-name import", "new statement after a multi-name import",
        "sole import as Z", "multi-name import as Z", "name spans only"])
def test_the_target_import_is_placed_by_the_block(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], use: str, expected: str
) -> None:
    root = _imported(tmp_path, monkeypatch, capsys, {"pkg/use.py": use})
    assert read(root, "pkg/use.py") == expected
    assert read(root, "pkg/compat.py") == COMPAT


def test_a_relative_import_is_spelled_from_the_importing_package(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    importers = {"pkg/a.py": ".compat", "pkg/lib/b.py": "..compat", "pkg/lib/deep/c.py": "...compat",
                 "pkg/other/d.py": "..compat"}
    root = _imported(tmp_path, monkeypatch, capsys, {
        "pkg/lib/core.py": CORE,
        **{f"{d}/__init__.py": "" for d in ("pkg/lib", "pkg/lib/deep", "pkg/other")},
        "pkg/compat.py": COMPAT.replace("from pkg.core", "from pkg.lib.core"),
        **{rel: f"from {module} import CONST, AcmeModel\n\nx = CONST, AcmeModel()\n" for rel, module in importers.items()},
    })
    homes = {"pkg/a.py": ".lib.core", "pkg/lib/b.py": ".core", "pkg/lib/deep/c.py": "..core", "pkg/other/d.py": "..lib.core"}
    assert {rel: read(root, rel) for rel in importers} == {
        rel: f"from {importers[rel]} import CONST\nfrom {home} import Model\n\nx = CONST, Model()\n"
        for rel, home in homes.items()
    }


@pytest.mark.parametrize(("home", "rel", "use", "expected"), [
    ("pkg/core/__init__.py", "pkg/sub/x.py", "from ..compat import AcmeModel\n", "from ..core import Model\n"),
    ("pkg/__init__.py", "pkg/sub/x.py", "from ..compat import AcmeModel\n", "from .. import Model\n"),
    ("pkg/__init__.py", "pkg/x.py", "from pkg.compat import AcmeModel\n", "from pkg import Model\n"),
], ids=["subpackage", "parent package, relative", "package, absolute"])
def test_a_package_home_is_named_by_its_module(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], home: str, rel: str, use: str,
    expected: str,
) -> None:
    module = home.removesuffix("/__init__.py").replace("/", ".")
    root = write_project(tmp_path / "proj", {
        "pkg/sub/__init__.py": "",
        home: "class Model:\n    pass\n",
        "pkg/compat.py": f"from {module} import Model\n\nAcmeModel = Model\n",
        rel: use + "\nx = AcmeModel()\n",
    })
    code, _out, err = run(root, _retarget("pkg/compat.py", "AcmeModel", "Model"), monkeypatch, capsys)
    assert (code, err) == (0, "")
    assert read(root, rel) == expected + "\nx = Model()\n"


def test_a_block_gets_one_import_per_home_across_map_entries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    entries = [{"file": "pkg/compat.py", "symbol": alias, "retarget": target}
               for alias, target in (("AcmeModel", "Model"), ("AcmePart", "Part"))]
    root = write_project(tmp_path / "proj", {
        "pkg/core.py": CORE,
        "pkg/compat.py": COMPAT,
        "pkg/use.py": "from pkg.compat import CONST, AcmeModel, AcmePart\n\nx = CONST, AcmeModel(), AcmePart()\n",
        "map.yaml": yaml.safe_dump(entries, sort_keys=False),
    })
    code, _out, err = run(root, ["--apply", "rename-map", "map.yaml"], monkeypatch, capsys)
    assert (code, err) == (0, "")
    assert read(root, "pkg/use.py") == "from pkg.compat import CONST\nfrom pkg.core import Model, Part\n\nx = CONST, Model(), Part()\n"


def test_an_unbound_module_attribute_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = write_project(tmp_path / "proj", {
        "pkg/models.py": MODELS,
        "pkg/compat.py": 'from pkg.models import AcmeModel\n\n__all__ = ["AcmeModel"]\n',
        "pkg/use.py": "import pkg.compat as c\n\nx = c.AcmeModel()\n",
    })
    before = file_tree(root)
    unbound = message("refactor.retarget-unbound", path="pkg/use.py", line=3, module="pkg/compat.py", name="Model")
    assert run(root, _retarget("pkg/models.py", "AcmeModel", "Model"), monkeypatch, capsys) == (1, "", f"{unbound}\n")
    assert file_tree(root) == before


@pytest.mark.parametrize(("files", "expected"), [
    ({"pkg/core.py": "class CoreModel:\n    pass\n", "pkg/compat.py": "from pkg.core import CoreModel as Model\n\nAcmeModel = Model\n"},
     "from pkg.core import CoreModel as Model\n\nx = Model()\n"),
    ({"pkg/_private.py": "class Model:\n    pass\n", "pkg/public.py": 'from pkg._private import Model\n\n__all__ = ["Model"]\n',
      "pkg/compat.py": "from pkg.public import Model\n\nAcmeModel = Model\n"},
     "from pkg.public import Model\n\nx = Model()\n"),
], ids=["under its exported name", "home not chased along a re-export chain"])
def test_the_home_is_the_import_of_the_alias_module(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], files: dict[str, str],
    expected: str,
) -> None:
    root = write_project(tmp_path / "proj", {**files, "pkg/use.py": "from pkg.compat import AcmeModel\n\nx = AcmeModel()\n"})
    code, _out, err = run(root, _retarget("pkg/compat.py", "AcmeModel", "Model"), monkeypatch, capsys)
    assert (code, err) == (0, "")
    assert read(root, "pkg/use.py") == expected


def test_a_reexported_alias_spelled_inside_its_target_keeps_its_declaration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    compat = "from pkg.core import BaseModel as Model\n"
    root = write_project(tmp_path / "proj", {
        "pkg/core.py": "class BaseModel:\n    pass\n",
        "pkg/compat.py": compat,
        "pkg/use.py": "from pkg.compat import Model\n\nx = Model()\n",
    })
    code, _out, err = run(root, _retarget("pkg/compat.py", "Model", "BaseModel"), monkeypatch, capsys)
    assert (code, err) == (0, "")
    assert read(root, "pkg/compat.py") == compat
    assert read(root, "pkg/use.py") == "from pkg.core import BaseModel\n\nx = BaseModel()\n"


def test_a_reexport_shim_binding_the_target_gets_no_import_for_its_own_use(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    shim = 'from pkg.models import Model, AcmeModel\n\n__all__ = ["Model", "AcmeModel"]\n\n\ndef make() -> object:\n    return AcmeModel()\n'
    root = write_project(tmp_path / "proj", {"pkg/models.py": MODELS, "pkg/compat.py": shim})
    code, _out, err = run(root, _retarget("pkg/models.py", "AcmeModel", "Model"), monkeypatch, capsys)
    assert (code, err) == (0, "")
    assert read(root, "pkg/compat.py") == shim.replace("return AcmeModel()", "return Model()")


def test_a_later_import_of_the_target_in_the_block_is_removed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    use = "from pkg.compat import CONST, AcmeModel\nfrom pkg.core import Model\n\nx = CONST, AcmeModel(), Model\n"
    root = _imported(tmp_path, monkeypatch, capsys, {"pkg/use.py": use})
    assert read(root, "pkg/use.py") == "from pkg.compat import CONST\nfrom pkg.core import Model\n\nx = CONST, Model(), Model\n"


def test_a_package_level_relative_import_keeps_its_separator(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = write_project(tmp_path / "proj", {
        "pkg/core.py": CORE,
        "pkg/__init__.py": "from pkg.core import Model\n\nAcmeModel = Model\n",
        "pkg/x.py": "from . import AcmeModel\n\nx = AcmeModel()\n",
    })
    code, _out, err = run(root, _retarget("pkg/__init__.py", "AcmeModel", "Model"), monkeypatch, capsys)
    assert (code, err) == (0, "")
    assert read(root, "pkg/x.py") == "from .core import Model\n\nx = Model()\n"


@pytest.mark.parametrize(("use", "expected"), [
    ("def f() -> object:\n    if True: from pkg.compat import CONST, AcmeModel\n    else: return None\n    return CONST, AcmeModel()\n",
     ("def f() -> object:\n    if True: from pkg.compat import CONST; from pkg.core import Model\n    else: return None\n"
      "    return CONST, Model()\n")),
    ("from pkg.compat import CONST, AcmeModel; x = CONST, AcmeModel()\n",
     "from pkg.compat import CONST; from pkg.core import Model; x = CONST, Model()\n"),
], ids=["after a compound statement's header", "before a later statement"])
def test_an_import_sharing_its_line_gets_the_target_import_beside_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], use: str, expected: str
) -> None:
    root = _imported(tmp_path, monkeypatch, capsys, {"pkg/use.py": use})
    assert read(root, "pkg/use.py") == expected


def test_a_module_attribute_of_a_target_without_a_definition_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = write_project(tmp_path / "proj", {
        "pkg/compat.py": "from itertools import chain\n\nAcmeChain = chain\n",
        "pkg/shim.py": "from pkg.compat import AcmeChain\n",
        "pkg/use.py": "import pkg.shim\n\nx = pkg.shim.AcmeChain()\n",
    })
    before = file_tree(root)
    unbound = message("refactor.retarget-unbound", path="pkg/use.py", line=3, module="pkg/shim.py", name="chain")
    assert run(root, _retarget("pkg/compat.py", "AcmeChain", "chain"), monkeypatch, capsys) == (1, "", f"{unbound}\n")
    assert file_tree(root) == before


def test_a_function_binding_the_target_later_gets_its_own_import(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    use = ("from pkg.core import Model\n\n\ndef f() -> object:\n    from pkg.compat import AcmeModel\n    value = AcmeModel()\n"
           "    from pkg.core import Model\n    return value, Model\n")
    root = _imported(tmp_path, monkeypatch, capsys, {"pkg/use.py": use})
    assert read(root, "pkg/use.py") == ("from pkg.core import Model\n\n\ndef f() -> object:\n    from pkg.core import Model\n"
                                        "    value = Model()\n    return value, Model\n")
