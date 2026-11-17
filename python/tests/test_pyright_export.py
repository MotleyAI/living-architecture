"""The occurrence-export preload under Node, against fake language-server bundles built around the bundled
basedpyright's own `CommandController`, and its export from the bundled server."""

from __future__ import annotations

import importlib.metadata
import os
import re
import shutil
import subprocess
from pathlib import Path

import basedpyright
import pytest
from nodejs_wheel.executable import ROOT_DIR
from project_files import write_project
from pydantic import BaseModel

from living_architecture import lang
from living_architecture.contract import language
from living_architecture.lang import ExportRequest, FactQuery, LanguageServer, OccurrenceIndex

NODE = Path(ROOT_DIR) / "bin" / "node"
BUNDLED = Path(next(iter(basedpyright.__path__))) / "dist" / "pyright-langserver.js"
VERSION_MODULE = '"../pyright-internal/src/version.json"(module) {{\n"use strict";\nmodule.exports = "{version}"\n\n}},\n'
REPORT = '\nconsole.log((require("worker_threads").isMainThread ? "main" : "worker") + ": loaded");\n'


def _controller() -> str:
    """The bundled language server's `CommandController` class, verbatim."""
    text = BUNDLED.read_text(encoding="utf-8")
    start = text.index("class CommandController {")
    end = re.compile(r"^}\n", re.MULTILINE).search(text, start)
    assert end is not None
    return text[start : end.end()]


def _ambient_line() -> str:
    """The bundled language server's line setting each workspace's ambient analysis, verbatim."""
    found = re.findall(r"^.*\.languageServerSettings\.enableAmbientAnalysis = trackFiles;\n",
                       BUNDLED.read_text(encoding="utf-8"), re.MULTILINE)
    assert len(found) == 1
    return found[0]


def _ambient(count: int) -> str:
    """A probe on `globalThis` returning the ambient analysis the bundle's line sets for tracked files."""
    body = "    const commandLineOptions = { languageServerSettings: {} };\n" + _ambient_line() * count
    return (f"globalThis.__laAmbientProbe = (trackFiles) => {{\n{body}"
            "    return commandLineOptions.languageServerSettings.enableAmbientAnalysis;\n};\n")


def _bundle_source(version: str | None, count: int, ambient: int = 1) -> str:
    modules = VERSION_MODULE.format(version=version) if version else ""
    return (f"(() => {{\nvar __webpack_modules__ = ({{\n{modules}}});\n" + _controller() * count + _ambient(ambient)
            + REPORT + "})();\n")


def _package(
    root: Path, version: str | None = "1.40.2", count: int = 1, name: str = "pyright-langserver.js", ambient: int = 1
) -> Path:
    """A fake basedpyright package; returns its entry, which requires dist/<name> like basedpyright's."""
    (root / "dist").mkdir(parents=True)
    (root / "dist" / name).write_text(_bundle_source(version, count, ambient), encoding="utf-8")
    entry = root / "langserver.index.js"
    entry.write_text(f"require('./dist/{name}');\n", encoding="utf-8")
    return entry


def _node(script: Path, result: Path, *, preload: Path | None = None) -> subprocess.CompletedProcess[str]:
    base = {k: v for k, v in os.environ.items() if k != "NODE_OPTIONS"}
    env = lang.pyright_export_env(base, result=result, versions=["1.40.2"], preload=preload or lang.PYRIGHT_EXPORT_PRELOAD)
    return subprocess.run([str(NODE), str(script)], env=env, capture_output=True, text=True, timeout=60, check=False)


def _outcome(result: Path) -> tuple[str, str] | None:
    found = lang.read_pyright_export(result)
    return None if found is None else (found.outcome, found.version)


@pytest.fixture
def result(tmp_path: Path) -> Path:
    (tmp_path / "out").mkdir()
    return tmp_path / "out" / "export.json"


def test_the_preload_ships_beside_the_11919_one() -> None:
    assert lang.PYRIGHT_EXPORT_PRELOAD.name == "pyright_export.cjs"
    assert lang.PYRIGHT_EXPORT_PRELOAD.parent == lang.PYRIGHT_PATCH_PRELOAD.parent
    assert lang.PYRIGHT_EXPORT_PRELOAD.is_file()


def test_the_bundled_version_is_verified() -> None:
    assert importlib.metadata.version("basedpyright") in language("python")["checker_export_versions"]


def test_env_sets_the_protocol_variables_after_inherited_node_options(tmp_path: Path) -> None:
    env = lang.pyright_export_env({"NODE_OPTIONS": "--max-old-space-size=4096", "X": "1"}, result=tmp_path / "r.json",
                                  versions=["1.40.2"])
    assert env["NODE_OPTIONS"] == f'--max-old-space-size=4096 --require "{lang.PYRIGHT_EXPORT_PRELOAD}"'
    assert (env["LA_PYRIGHT_EXPORT_RESULT"], env["LA_PYRIGHT_EXPORT_VERSIONS"], env["X"]) == (
        str(tmp_path / "r.json"), '["1.40.2"]', "1")


def test_verified_version_is_patched_in_memory(tmp_path: Path, result: Path) -> None:
    entry = _package(tmp_path / "pkg")
    bundle = tmp_path / "pkg" / "dist" / "pyright-langserver.js"
    before = bundle.read_bytes()
    proc = _node(entry, result)
    assert (proc.returncode, proc.stdout) == (0, "main: loaded\n"), proc.stderr
    assert _outcome(result) == ("patched", "1.40.2")
    assert bundle.read_bytes() == before


def test_unlisted_version_is_unverified_and_node_exits_2(tmp_path: Path, result: Path) -> None:
    proc = _node(_package(tmp_path / "pkg", version="1.39.10"), result)
    assert proc.returncode == 2
    assert "loaded" not in proc.stdout
    assert _outcome(result) == ("unverified", "1.39.10")


@pytest.mark.parametrize("count", [0, 2], ids=["absent", "twice"])
def test_anchors_not_matched_exactly_once_are_a_mismatch(tmp_path: Path, result: Path, count: int) -> None:
    proc = _node(_package(tmp_path / "pkg", count=count), result)
    assert proc.returncode == 2
    assert "loaded" not in proc.stdout
    assert _outcome(result) == ("mismatch", "1.40.2")


@pytest.mark.parametrize("ambient", [0, 2], ids=["absent", "twice"])
def test_an_ambient_analysis_line_not_matched_exactly_once_is_a_mismatch(
    tmp_path: Path, result: Path, ambient: int
) -> None:
    proc = _node(_package(tmp_path / "pkg", ambient=ambient), result)
    assert proc.returncode == 2
    assert "loaded" not in proc.stdout
    assert _outcome(result) == ("mismatch", "1.40.2")


def test_the_patched_bundle_runs_no_ambient_analysis(tmp_path: Path, result: Path) -> None:
    entry = _package(tmp_path / "pkg")
    main = tmp_path / "main.js"
    main.write_text(f"require({str(entry)!r});\nconsole.log('ambient: ' + globalThis.__laAmbientProbe(true));\n",
                    encoding="utf-8")
    proc = _node(main, result)
    assert (proc.returncode, proc.stdout) == (0, "main: loaded\nambient: false\n"), proc.stderr


@pytest.mark.parametrize("name",["pyright.js", "other.js"])
def test_bundles_other_than_the_language_server_are_left_alone(tmp_path: Path, result: Path, name: str) -> None:
    proc = _node(_package(tmp_path / "pkg", name=name), result)
    assert (proc.returncode, proc.stdout) == (0, "main: loaded\n"), proc.stderr
    assert not result.exists()


def test_a_bundle_without_the_version_module_is_left_alone(tmp_path: Path, result: Path) -> None:
    proc = _node(_package(tmp_path / "pkg", version=None), result)
    assert (proc.returncode, proc.stdout) == (0, "main: loaded\n"), proc.stderr
    assert not result.exists()


def test_result_dir_holds_only_the_result(tmp_path: Path, result: Path) -> None:
    _node(_package(tmp_path / "pkg"), result)
    assert [p.name for p in result.parent.iterdir()] == [result.name]


def test_worker_thread_writes_nothing(tmp_path: Path, result: Path) -> None:
    _package(tmp_path / "pkg")
    main = tmp_path / "main.js"
    bundle = tmp_path / "pkg" / "dist" / "pyright-langserver.js"
    main.write_text(f"new (require('worker_threads').Worker)({str(bundle)!r});\n", encoding="utf-8")
    proc = _node(main, result)
    assert (proc.returncode, proc.stdout) == (0, "worker: loaded\n"), proc.stderr
    assert not result.exists()


def test_preload_path_with_spaces(tmp_path: Path, result: Path) -> None:
    preload = tmp_path / "with spaces" / lang.PYRIGHT_EXPORT_PRELOAD.name
    preload.parent.mkdir()
    shutil.copyfile(lang.PYRIGHT_EXPORT_PRELOAD, preload)
    proc = _node(_package(tmp_path / "pkg"), result, preload=preload)
    assert (proc.returncode, proc.stdout) == (0, "main: loaded\n"), proc.stderr
    assert _outcome(result) == ("patched", "1.40.2")


LEAF = ("from enum import Enum\n\nfrom pydantic import BaseModel\n\n\nclass Kind(Enum):\n    A = 1\n\n\n"
        "class Leaf(BaseModel):\n    kind: Kind\n")
MODEL = ("from pydantic import BaseModel\n\nfrom pkg.leaf import Leaf\n\n\nclass Mid(BaseModel):\n    leaf: Leaf\n\n\n"
         "class Top(BaseModel):\n    mid: Mid\n    tags: list[str]\n\n\ntop: Top | None = None\n")


class PydanticExport(BaseModel):
    root: Path
    model: Path
    leaf: Path
    index: OccurrenceIndex


@pytest.fixture(scope="module")
def pydantic_export(tmp_path_factory: pytest.TempPathFactory) -> PydanticExport:
    """One export over a pydantic project: definitions at a use of `Top`, at a `BaseModel` base and at `list`."""
    root = write_project(tmp_path_factory.mktemp("export") / "p", {"pkg/leaf.py": LEAF, "pkg/m.py": MODEL}).resolve()
    model, leaf = root / "pkg" / "m.py", root / "pkg" / "leaf.py"
    offsets = [MODEL.rindex("Top"), MODEL.index("(BaseModel)") + 1, MODEL.index("list[")]
    with LanguageServer(root) as server:
        server.open(leaf, LEAF)
        server.open(model, MODEL)
        index = server.export(ExportRequest(names=[], files=[], facts=[
            FactQuery(path=model, offset=offset, kinds=("definition",)) for offset in offsets]))
    return PydanticExport(root=root, model=model, leaf=leaf, index=index)


def test_follow_stays_out_of_library_and_typeshed_files(pydantic_export: PydanticExport) -> None:
    followed = pydantic_export.index.followed
    assert followed
    assert [str(f.path) for f in followed if not f.path.is_relative_to(pydantic_export.root)] == []


def test_a_first_party_chain_is_followed_to_its_end(pydantic_export: PydanticExport) -> None:
    model, leaf = pydantic_export.model, pydantic_export.leaf
    facts = {(f.path, f.offset): {(d.path, d.start) for d in f.definition} for f in pydantic_export.index.followed}
    assert (model, MODEL.index("class Mid") + len("class ")) in facts[(model, MODEL.index("mid: Mid") + len("mid: "))]
    assert (leaf, LEAF.index("class Leaf") + len("class ")) in facts[(model, MODEL.index("leaf: Leaf") + len("leaf: "))]
    assert (leaf, LEAF.index("class Kind") + len("class ")) in facts[(leaf, LEAF.index("kind: Kind") + len("kind: "))]


def test_a_direct_definition_in_a_library_or_typeshed_is_answered(pydantic_export: PydanticExport) -> None:
    _, base, builtin = pydantic_export.index.answers
    assert any("pydantic" in d.path.parts for d in base.definition)
    assert any(d.path.name == "builtins.pyi" for d in builtin.definition)


CLASSES = ("from typing import cast\n\nfrom pydantic import BaseModel\n\n\nclass Root:\n    def own(self) -> int:\n"
           "        return 0\n\n\nclass Mid(Root):\n    pass\n\n\nclass Cast(cast(\"type[Mid]\", object)):\n    pass\n\n\n"
           "class Model(BaseModel):\n    pass\n")


@pytest.fixture(scope="module")
def class_export(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, OccurrenceIndex]:
    """One export of the class facts of `Mid`, `Cast` and `Model`, looking up `own` and `model_dump`."""
    root = write_project(tmp_path_factory.mktemp("classes") / "p", {"pkg/c.py": CLASSES}).resolve()
    path = root / "pkg" / "c.py"
    offsets = [CLASSES.index(f"class {name}") + len("class ") for name in ("Mid", "Cast", "Model")]
    with LanguageServer(root) as server:
        server.open(path, CLASSES)
        index = server.export(ExportRequest(names=[], files=[], members=["own", "model_dump"], facts=[
            FactQuery(path=path, offset=offset, kinds=("class",)) for offset in offsets]))
    return path, index


def test_a_class_fact_lists_its_ancestors_by_name(class_export: tuple[Path, OccurrenceIndex]) -> None:
    path, index = class_export
    mid, cast_base, _ = index.answers
    root_name = (path, CLASSES.index("class Root") + len("class "))
    mid_name = (path, CLASSES.index("class Mid") + len("class "))
    assert next((s.path, s.start) for s in mid.ancestors) == root_name
    assert [(s.path, s.start) for s in cast_base.ancestors][:2] == [mid_name, root_name]
    assert mid.kinds == ("class",)


def test_a_class_fact_names_only_members_a_library_class_declares(class_export: tuple[Path, OccurrenceIndex]) -> None:
    mid, cast_base, model = class_export[1].answers
    assert (mid.members, cast_base.members, model.members) == ((), (), ("model_dump",))
    assert any("pydantic" in s.path.parts for s in model.ancestors)


def test_a_class_fact_at_a_name_that_is_no_class_is_empty(tmp_path: Path) -> None:
    root = write_project(tmp_path / "p", {"pkg/c.py": CLASSES}).resolve()
    path = root / "pkg" / "c.py"
    with LanguageServer(root) as server:
        server.open(path, CLASSES)
        index = server.export(ExportRequest(names=[], files=[], members=["own"], facts=[
            FactQuery(path=path, offset=CLASSES.index("own"), kinds=("class",))]))
    assert (index.answers[0].ancestors, index.answers[0].members) == ((), ())
