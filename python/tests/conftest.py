import importlib.util
import json
import os
import shutil
import subprocess
import sys
from collections.abc import Callable
from functools import cache
from pathlib import Path

import pytest
from rope.refactor import patchedast

from living_architecture.contract import snapshot_dir

SCRIPTS_DIR = snapshot_dir() / "scripts"


def pytest_configure(config: pytest.Config) -> None:
    """Golden updates write from one process: undo xdist's `-n`, even an explicit one."""
    if os.environ.get("LA_UPDATE_GOLDENS") == "1":
        config.option.numprocesses = 0
        config.option.dist = "no"
        config.option.tx = []

# Stand-in `gh`: first route whose tokens all appear in argv wins; `--jq`/`-q`
# filters are applied with the real jq; every call is logged with any --input payload.
FAKE_GH = """\
import json, os, subprocess, sys

argv = sys.argv[1:]
with open(os.environ["FAKE_GH_ROUTES"]) as fh:
    routes = json.load(fh)
entry = {"argv": argv}
if "--input" in argv:
    with open(argv[argv.index("--input") + 1]) as fh:
        entry["input"] = fh.read()
with open(os.environ["FAKE_GH_LOG"], "a") as fh:
    fh.write(json.dumps(entry) + "\\n")
for route in routes:
    if all(tok in argv for tok in route["match"]):
        out = route.get("stdout", "")
        for flag in ("--jq", "-q"):
            if flag in argv:
                jq = subprocess.run(["jq", "-rc", argv[argv.index(flag) + 1]], input=out,
                                    capture_output=True, text=True, check=False)
                sys.stderr.write(jq.stderr)
                out = jq.stdout
        sys.stdout.write(out)
        sys.exit(route.get("exit", 0))
sys.stderr.write("fake gh: no route for " + " ".join(argv) + "\\n")
sys.exit(1)
"""


class FakeGh:
    def __init__(self, tmp_path: Path) -> None:
        self.bin = tmp_path / "fakebin"
        self.bin.mkdir()
        self.routes_file = tmp_path / "routes.json"
        self.log_file = tmp_path / "gh.log"
        self.tmp = tmp_path
        gh = self.bin / "gh"
        gh.write_text(f"#!{sys.executable}\n{FAKE_GH}")
        gh.chmod(0o755)
        self.route()

    def route(self, *routes: tuple[list[str], object] | tuple[list[str], object, int]) -> None:
        """Each route: (argv tokens, stdout as str or JSON-able, [exit code])."""
        out = []
        for r in routes:
            stdout = r[1] if isinstance(r[1], str) else json.dumps(r[1])
            out.append({"match": r[0], "stdout": stdout, "exit": r[2] if len(r) > 2 else 0})
        self.routes_file.write_text(json.dumps(out))

    def calls(self) -> list[dict]:
        if not self.log_file.exists():
            return []
        return [json.loads(line) for line in self.log_file.read_text().splitlines()]

    def env(self) -> dict[str, str]:
        return {
            **os.environ,
            "PATH": f"{self.bin}{os.pathsep}{os.environ['PATH']}",
            "FAKE_GH_ROUTES": str(self.routes_file),
            "FAKE_GH_LOG": str(self.log_file),
            "TMPDIR": str(self.tmp),
        }


@pytest.fixture
def fake_gh(tmp_path: Path) -> FakeGh:
    return FakeGh(tmp_path)


@pytest.fixture
def run_script(fake_gh: FakeGh) -> Callable[..., subprocess.CompletedProcess[str]]:
    def run(script: str, *args: str, stdin: str | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", str(SCRIPTS_DIR / script), *args],
            input=stdin if stdin is not None else "",
            capture_output=True,
            text=True,
            env=fake_gh.env(),
            cwd=fake_gh.tmp,
            check=False,
        )

    return run


REPO_SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
# The release manifests and lockfiles, as templates over the package version and one dependency.
RELEASE_MANIFESTS = {
    "python/pyproject.toml": '[project]\nname = "living-architecture"\nversion = "{version}"\ndependencies = ["pyyaml{dep}"]\n',
    "python/uv.lock": (
        'version = 1\n\n[[package]]\nname = "living-architecture"\nversion = "{version}"\n\n'
        '[[package]]\nname = "pyyaml"\nversion = "{dep}"\n'
    ),
    "node/package.json": '{{\n  "name": "living-architecture",\n  "version": "{version}",\n  "dependencies": {{"ajv": "{dep}"}}\n}}\n',
    "node/package-lock.json": (
        '{{\n  "name": "living-architecture",\n  "version": "{version}",\n  "packages": {{\n'
        '    "": {{"name": "living-architecture", "version": "{version}"}},\n'
        '    "node_modules/ajv": {{"version": "{dep}"}}\n  }}\n}}\n'
    ),
}
RELEASE_FILES = {
    "shared/cli.yaml": "commands: {}\n",
    "conformance/README.md": "# corpus\n",
    "python/src/living_architecture/__init__.py": "",
    "python/src/living_architecture/contract/data/CONTRACT_HASH": "h\n",
    "python/tests/test_x.py": "",
    "node/src/index.ts": "export {};\n",
    "node/src/contract/data/CONTRACT_HASH": "h\n",
    "node/scripts/build.mjs": "",
    "node/tsconfig.json": "{}\n",
    "node/tsconfig.build.json": "{}\n",
    "plugin/skills/pr/SKILL.md": "skill\n",
    "docs/index.md": "docs\n",
    "README.md": "readme\n",
}


class ReleaseRepo:
    """A git repo in the twins' layout with this checkout's scripts/, for the release rule."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.deps = {"python/pyproject.toml": ">=6", "python/uv.lock": "6.0.2", "node/package.json": "^8.20.0",
                     "node/package-lock.json": "8.20.0"}
        shutil.copytree(REPO_SCRIPTS, root / "scripts")
        for rel, text in RELEASE_FILES.items():
            self.write(rel, text)
        home = root.parent / f"{root.name}-home"
        home.mkdir()
        (home / ".gitconfig").write_text("", encoding="utf-8")
        self.env = {
            **os.environ, "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": str(home / ".gitconfig"),
            "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
            "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid",
        }
        self.git("init", "-q", "-b", "main")

    def git(self, *args: str) -> str:
        return subprocess.run(["git", *args], cwd=self.root, env=self.env, capture_output=True, text=True, check=True).stdout

    def write(self, rel: str, text: str) -> None:
        (self.root / rel).parent.mkdir(parents=True, exist_ok=True)
        (self.root / rel).write_text(text, encoding="utf-8")

    def change(self, rel: str) -> None:
        """Append a line to `rel`, creating it if absent."""
        path = self.root / rel
        self.write(rel, (path.read_text(encoding="utf-8") if path.exists() else "") + "changed\n")

    def commit(self, message: str = "change") -> None:
        self.git("add", "-A")
        self.git("commit", "-q", "--allow-empty", "-m", message)

    def bump(self, version: str, *, plugin: str | None = None) -> None:
        """Commit every manifest and lockfile at `version` (plugin.json at `plugin` when given)."""
        for rel, template in RELEASE_MANIFESTS.items():
            self.write(rel, template.format(version=version, dep=self.deps[rel]))
        self.write("plugin/.claude-plugin/plugin.json", f'{{"name": "la", "version": "{plugin or version}"}}\n')
        self.commit(f"release {version}")

    def tag(self, name: str, *, annotated: bool = False) -> None:
        self.git("tag", *(["-a", "-m", name] if annotated else []), name)

    def release(self, version: str, *, annotated: bool = False, plugin: str | None = None) -> None:
        self.bump(version, plugin=plugin)
        self.tag(f"v{version}", annotated=annotated)

    def shallow_clone(self, tag: str) -> Path:
        clone = self.root.parent / f"{self.root.name}-shallow"
        subprocess.run(["git", "clone", "-q", "--depth", "1", "--branch", tag, f"file://{self.root}", str(clone)],
                       env=self.env, capture_output=True, check=True)
        return clone

    def release_check(self, tag: str, *, root: Path | None = None) -> subprocess.CompletedProcess[str]:
        """`scripts/release-check <tag>` in this repo, or in the clone at `root`."""
        checkout = root or self.root
        return subprocess.run([sys.executable, str(checkout / "scripts" / "release-check"), tag], cwd=checkout,
                              env=self.env, capture_output=True, text=True, check=False)


@pytest.fixture
def release_repo(tmp_path: Path) -> ReleaseRepo:
    return ReleaseRepo(tmp_path / "repo")


@cache
def _unpatched_walker() -> type:
    """rope's own `_PatchingASTWalker`, from a private copy of `patchedast` that no patch touches."""
    spec = importlib.util.spec_from_file_location("_unpatched_patchedast", patchedast.__file__)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module._PatchingASTWalker


@pytest.fixture
def restore_rope_visitor(monkeypatch: pytest.MonkeyPatch) -> Callable[[str], None]:
    """Put one of rope's own walker visitors back in place of its patch, for this test."""

    def restore(name: str) -> None:
        monkeypatch.setattr(patchedast._PatchingASTWalker, name, getattr(_unpatched_walker(), name))

    return restore


@pytest.fixture
def annotation_gap() -> str:
    """rope's own `_arg` leaves the line-3 annotation unwalked; the walk then drifts and crashes on line 8."""
    return (
        "from pkg.a import foo\n"
        "\n"
        'def f(p: F("(") = None):\n'
        "    a = 1\n"
        "    b = 2\n"
        "    c = 3\n"
        "    d = 4\n"
        "    e = foo()\n"
        "    return g(a)\n"
    )
