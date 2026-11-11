"""The pyright#11919 preload under Node, against fake basedpyright bundles."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest
from nodejs_wheel.executable import ROOT_DIR

from living_architecture import lang

NODE = Path(ROOT_DIR) / "bin" / "node"
CONDITION = "!isGetTypeFromCodeFlowPending(referenceKeyWithSymbolId) &&"
VERSION_MODULE = '"../pyright-internal/src/version.json"(module) {{\n"use strict";\nmodule.exports = "{version}"\n\n}},\n'
REPORT = """
function isGetTypeFromCodeFlowPending(key) {{ return key !== undefined; }}
const referenceKeyWithSymbolId = "k";
const results = [];
{checks}
const where = require("worker_threads").isMainThread ? "main" : "worker";
console.log(where + ": " + (results.length && results.every(Boolean) ? "patched" : "unpatched"));
"""
CHECK = f"results.push(\n    {CONDITION}\n    true);\n"


def _bundle_source(version: str | None, count: int = 1) -> str:
    modules = VERSION_MODULE.format(version=version) if version else ""
    return (f"(() => {{\nvar __webpack_modules__ = ({{\n{modules}}});\n"
            + REPORT.format(checks=CHECK * count) + "})();\n")


def _package(root: Path, version: str | None = "1.40.2", count: int = 1, name: str = "pyright.js") -> Path:
    """A fake basedpyright package; returns its CLI entry, which requires dist/<name> like basedpyright's index.js."""
    (root / "dist").mkdir(parents=True)
    (root / "dist" / name).write_text(_bundle_source(version, count), encoding="utf-8")
    entry = root / "index.js"
    entry.write_text(f"require('./dist/{name}');\n", encoding="utf-8")
    return entry


def _node(script: Path, result: Path, *, preload: Path | None = None) -> subprocess.CompletedProcess[str]:
    base = {k: v for k, v in os.environ.items() if k != "NODE_OPTIONS"}
    env = lang.pyright_patch_env(base, result=result, versions=["1.40.2"], preload=preload or lang.PYRIGHT_PATCH_PRELOAD)
    return subprocess.run([str(NODE), str(script)], env=env, capture_output=True, text=True, timeout=60, check=False)


@pytest.fixture
def result(tmp_path: Path) -> Path:
    (tmp_path / "out").mkdir()
    return tmp_path / "out" / "patch.json"


def test_fake_bundle_is_unpatched_without_the_preload(tmp_path: Path) -> None:
    entry = _package(tmp_path / "pkg")
    proc = subprocess.run([str(NODE), str(entry)], capture_output=True, text=True, timeout=60, check=False)
    assert (proc.returncode, proc.stdout) == (0, "main: unpatched\n")


def test_verified_version_is_patched_in_memory(tmp_path: Path, result: Path) -> None:
    entry = _package(tmp_path / "pkg")
    bundle = tmp_path / "pkg" / "dist" / "pyright.js"
    before = bundle.read_bytes()
    proc = _node(entry, result)
    assert (proc.returncode, proc.stdout) == (0, "main: patched\n"), proc.stderr
    assert lang.read_pyright_patch(result) == lang.PyrightPatch(outcome="patched", version="1.40.2", count=1)
    assert bundle.read_bytes() == before


def test_result_dir_holds_only_the_result(tmp_path: Path, result: Path) -> None:
    _node(_package(tmp_path / "pkg"), result)
    assert [p.name for p in result.parent.iterdir()] == [result.name]


def test_unlisted_version_is_unverified_and_node_exits_2(tmp_path: Path, result: Path) -> None:
    proc = _node(_package(tmp_path / "pkg", version="1.39.10"), result)
    assert proc.returncode == 2
    assert "patched" not in proc.stdout
    assert lang.read_pyright_patch(result) == lang.PyrightPatch(outcome="unverified", version="1.39.10", count=1)


@pytest.mark.parametrize("count", [0, 2])
def test_condition_not_exactly_once_is_a_mismatch(tmp_path: Path, result: Path, count: int) -> None:
    proc = _node(_package(tmp_path / "pkg", count=count), result)
    assert proc.returncode == 2
    assert "patched" not in proc.stdout
    assert lang.read_pyright_patch(result) == lang.PyrightPatch(outcome="mismatch", version="1.40.2", count=count)


def test_pyright_js_without_the_version_module_is_left_alone(tmp_path: Path, result: Path) -> None:
    proc = _node(_package(tmp_path / "pkg", version=None), result)
    assert (proc.returncode, proc.stdout) == (0, "main: unpatched\n"), proc.stderr
    assert not result.exists()


def test_unrelated_file_is_left_alone(tmp_path: Path, result: Path) -> None:
    proc = _node(_package(tmp_path / "pkg", name="other.js"), result)
    assert (proc.returncode, proc.stdout) == (0, "main: unpatched\n"), proc.stderr
    assert not result.exists()


def test_worker_thread_is_patched_and_writes_nothing(tmp_path: Path, result: Path) -> None:
    _package(tmp_path / "pkg")
    main = tmp_path / "main.js"
    main.write_text(
        "const { Worker } = require('worker_threads');\n"
        f"new Worker({str(tmp_path / 'pkg' / 'dist' / 'pyright.js')!r});\n",
        encoding="utf-8",
    )
    proc = _node(main, result)
    assert (proc.returncode, proc.stdout) == (0, "worker: patched\n"), proc.stderr
    assert not result.exists()


def test_preload_path_with_spaces(tmp_path: Path, result: Path) -> None:
    preload = tmp_path / "with spaces" / lang.PYRIGHT_PATCH_PRELOAD.name
    preload.parent.mkdir()
    shutil.copyfile(lang.PYRIGHT_PATCH_PRELOAD, preload)
    proc = _node(_package(tmp_path / "pkg"), result, preload=preload)
    assert (proc.returncode, proc.stdout) == (0, "main: patched\n"), proc.stderr
    assert lang.read_pyright_patch(result) == lang.PyrightPatch(outcome="patched", version="1.40.2", count=1)
