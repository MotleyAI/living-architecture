"""One entry module per command, and what a lightweight command loads."""

import ast
import importlib
import json
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
WORKSPACE = PROJECT_ROOT.parent
# Per distribution: its member directory and its import package.
PACKAGES = {"dr": "deterministic_refactor", "la": "living_architecture"}
SCRIPT_PACKAGES: dict[str, str] = {
    command: package
    for member, package in PACKAGES.items()
    for command in tomllib.loads((WORKSPACE / member / "pyproject.toml").read_text(encoding="utf-8"))["project"]["scripts"]
}
SCRIPTS: dict[str, str] = {
    command: target
    for member in PACKAGES
    for command, target in tomllib.loads((WORKSPACE / member / "pyproject.toml").read_text(encoding="utf-8"))[
        "project"
    ]["scripts"].items()
}
CLI_INITS = {package: WORKSPACE / member / "src" / package / "cli" / "__init__.py" for member, package in PACKAGES.items()}
COMMAND_PACKAGES = [
    "living_architecture.affected", "living_architecture.archcheck", "living_architecture.c4",
    "living_architecture.conventions", "living_architecture.doctor", "living_architecture.review",
    "deterministic_refactor.refactor", "deterministic_refactor.twin", "deterministic_refactor.typecheck",
]
HEAVY = [
    "rope", "deterministic_refactor.refactor", "deterministic_refactor.typecheck",
    *(f"living_architecture.{p}" for p in ("archcheck", "c4", "conventions", "affected")),
]
SHIMS = ["la-fetch-coderabbit-threads", "la-reply-invalid-coderabbit", "la-reply-to-pr-thread", "la-fetch-failed-pr-checks",
         "la-wait-for-reviews", "la-pr-reviewers"]
LIGHTWEIGHT = [("la-config", ["get", "tracker"]), ("la-doctor", ["--twin"]), ("la-doctor", ["--contract-hash"]),
               *((shim, ["--help"]) for shim in SHIMS)]
# Calls one entry point with `os.execvp` stubbed out, then writes how it ended and the loaded module names.
RUNNER = """
import importlib, json, os, sys
out, target, *argv = sys.argv[1:]
module, function = target.split(":")
class Exec(Exception):
    pass
def stub(*_args):
    raise Exec
os.execvp = stub
try:
    end = getattr(importlib.import_module(module), function)(argv) or 0
except SystemExit as exit:
    end = exit.code or 0
except Exec:
    end = "exec"
with open(out, "w", encoding="utf-8") as fh:
    json.dump({"end": end, "modules": sorted(sys.modules)}, fh)
"""


def _snake(command: str) -> str:
    return command.replace("-", "_")


def test_every_command_has_its_own_entry_module() -> None:
    assert SCRIPTS == {
        command: f"{SCRIPT_PACKAGES[command]}.cli.{_snake(command)}:{_snake(command)}" for command in SCRIPTS
    }


@pytest.mark.parametrize("command", SCRIPTS)
def test_every_entry_point_resolves(command: str) -> None:
    module, function = SCRIPTS[command].split(":")
    assert callable(getattr(importlib.import_module(module), function))


def _cli_init(package: str) -> ast.Module:
    return ast.parse(CLI_INITS[package].read_text(encoding="utf-8"))


def _absolute(node: ast.ImportFrom, top: str) -> str:
    """The module a `from` import in `top`'s `cli/__init__.py` names, relative ones resolved."""
    if not node.level:
        return node.module or ""
    package = [top, "cli"][: 3 - node.level]
    return ".".join([*package, *([node.module] if node.module else [])])


@pytest.mark.parametrize("package", PACKAGES.values())
def test_the_cli_package_imports_no_command_package(package: str) -> None:
    imported: set[str] = set()
    for node in ast.walk(_cli_init(package)):
        if isinstance(node, ast.ImportFrom):
            base = _absolute(node, package)
            imported |= {base, *(f"{base}.{alias.name}" for alias in node.names)}
        elif isinstance(node, ast.Import):
            imported |= {alias.name for alias in node.names}
    assert sorted(m for m in imported if any(m == c or m.startswith(c + ".") for c in COMMAND_PACKAGES)) == []


@pytest.mark.parametrize("package", PACKAGES.values())
def test_the_cli_packages_define_nothing(package: str) -> None:
    assert [n for n in _cli_init(package).body if not isinstance(n, ast.Expr | ast.ImportFrom)] == []


@pytest.mark.parametrize(("command", "argv"), LIGHTWEIGHT, ids=lambda v: " ".join(v) if isinstance(v, list) else v)
def test_lightweight_commands_load_no_heavy_package(command: str, argv: list[str], tmp_path: Path) -> None:
    out = tmp_path / "modules.json"
    proc = subprocess.run([sys.executable, "-c", RUNNER, str(out), SCRIPTS[command], *argv], cwd=PROJECT_ROOT,
                          capture_output=True, text=True, timeout=60, check=False)
    assert out.is_file(), proc.stderr
    found = json.loads(out.read_text(encoding="utf-8"))
    assert found["end"] == ("exec" if command in SHIMS else 0), proc.stderr
    assert [m for m in found["modules"] if any(m == h or m.startswith(h + ".") for h in HEAVY)] == []
