import json
import os
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

from conformance_runner import fake_gh_cli
from living_architecture.contract import snapshot_dir
from trmv.contract import compute_hash

SCRIPTS_DIR = snapshot_dir() / "scripts"


def pytest_configure(config: pytest.Config) -> None:
    """Golden updates write from one process: undo xdist's `-n`, even an explicit one."""
    if os.environ.get("LA_UPDATE_GOLDENS") == "1":
        config.option.numprocesses = 0
        config.option.dist = "no"
        config.option.tx = []

Route = tuple[list[str], object] | tuple[list[str], object, int] | tuple[list[str], object, int, str]


class FakeGh:
    def __init__(self, tmp_path: Path) -> None:
        self.bin = tmp_path / "fakebin"
        self.bin.mkdir()
        self.routes_file = tmp_path / "routes.json"
        self.log_file = tmp_path / "gh.log"
        self.tmp = tmp_path
        fake_gh_cli.install(self.bin)
        self.route()

    def route(self, *routes: Route | dict) -> None:
        """Each route: (argv tokens, stdout as str or JSON-able, [exit code, [stderr]]), or a case-format route dict."""
        specs = [r if isinstance(r, dict) else {"match": r[0], "stdout": r[1], "exit": r[2] if len(r) > 2 else 0,
                                                "stderr": r[3] if len(r) > 3 else ""}
                 for r in routes]
        fake_gh_cli.write_routes(self.routes_file, specs)

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


@pytest.fixture(autouse=True)
def cache_dir(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Each test's own occurrence-index cache, outside its project."""
    path = tmp_path_factory.mktemp("la-cache")
    monkeypatch.setenv("LA_CACHE_DIR", str(path))
    return path


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
            timeout=90,
            check=False,
        )

    return run


REPO_SCRIPTS = next(p for p in Path(__file__).resolve().parents if (p / "shared").is_dir() and (p / "plugin").is_dir()) / "scripts"
FORMATS_CONFIG = "shared/trmv/config.yaml"
RELEASE_FILES = {
    "shared/trmv/cli.yaml": "commands: {trmv-x: {}}\n",
    FORMATS_CONFIG: (
        "files: [trmv.yaml, living-architecture.yaml]\nformats:\n"
        "  trmv.yaml: [0.4.0]\n  living-architecture.yaml: [0.4.0]\n"
    ),
    "shared/la/cli.yaml": "commands: {la-x: {}}\n",
    "conformance/trmv/README.md": "# trmv corpus\n",
    "conformance/la/README.md": "# la corpus\n",
    "python/trmv/src/trmv/__init__.py": "",
    "python/la/src/living_architecture/__init__.py": "",
    "python/la/tests/test_x.py": "",
    "node/scripts/conformance.mjs": "",
    "node/trmv/src/index.ts": "export {};\n",
    "node/la/src/index.ts": "export {};\n",
    "node/trmv/scripts/build.mjs": "",
    "node/la/scripts/build.mjs": "",
    "node/trmv/tsconfig.json": "{}\n",
    "node/la/tsconfig.json": "{}\n",
    "node/la/tsconfig.build.json": "{}\n",
    "plugin/la/skills/pr/SKILL.md": "skill\n",
    "docs/index.md": "docs\n",
    "README.md": "readme\n",
}
# Each twin's snapshot hash file, by the package whose contract it vendors.
RELEASE_SNAPSHOTS = {
    "python/trmv/src/trmv/contract/data/CONTRACT_HASH": "trmv",
    "python/la/src/living_architecture/contract/data/CONTRACT_HASH": "la",
    "node/trmv/src/contract/data/CONTRACT_HASH": "trmv",
    "node/la/src/contract/data/CONTRACT_HASH": "la",
}
# The manifests and lockfiles naming a third-party dependency, each pinning it by its own spec.
DEPENDENCY_MANIFESTS = [
    "python/trmv/pyproject.toml", "python/la/pyproject.toml", "python/uv.lock", "node/trmv/package.json",
    "node/la/package.json", "node/package-lock.json",
]


def _series(version: str) -> tuple[str, str]:
    major, minor = version.split(".")[:2]
    return f"{major}.{minor}.0", f"{major}.{int(minor) + 1}"


class ReleaseRepo:
    """A git repo in the two-package layout with this checkout's scripts/, for the release rule."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.deps = {"python/trmv/pyproject.toml": ">=6", "python/la/pyproject.toml": ">=6", "python/uv.lock": "6.0.2",
                     "node/trmv/package.json": "^8.20.0", "node/la/package.json": "^8.20.0",
                     "node/package-lock.json": "8.20.0"}
        self.overrides: dict[str, str] = {}
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

    def manifests(self, version: str) -> dict[str, str]:
        """Every manifest and lockfile at `version`, la pinning trmv to its minor."""
        base, upper = _series(version)
        pin, tilde, deps = f">={base},<{upper}", f"~{base}", self.deps
        return {
            "python/pyproject.toml": '[tool.uv.workspace]\nmembers = ["trmv", "la", "conformance"]\n',
            "python/trmv/pyproject.toml": (
                f'[project]\nname = "type-rename-move"\nversion = "{version}"\n'
                f'dependencies = ["pyyaml{deps["python/trmv/pyproject.toml"]}"]\n'
            ),
            "python/la/pyproject.toml": (
                f'[project]\nname = "living-architecture"\nversion = "{version}"\n'
                f'dependencies = ["type-rename-move{pin}", "pyyaml{deps["python/la/pyproject.toml"]}"]\n'
            ),
            "python/uv.lock": (
                f'version = 1\n\n[[package]]\nname = "type-rename-move"\nversion = "{version}"\n'
                f'source = {{ editable = "trmv" }}\n\n[[package]]\nname = "living-architecture"\nversion = "{version}"\n'
                f'source = {{ editable = "la" }}\n\n[[package]]\nname = "pyyaml"\nversion = "{deps["python/uv.lock"]}"\n'
            ),
            "node/package.json": '{"name": "workspace", "private": true, "workspaces": ["trmv", "la"]}\n',
            "node/trmv/package.json": (
                f'{{"name": "type-rename-move", "version": "{version}",'
                f' "dependencies": {{"ajv": "{deps["node/trmv/package.json"]}"}}}}\n'
            ),
            "node/la/package.json": (
                f'{{"name": "living-architecture", "version": "{version}",'
                f' "dependencies": {{"type-rename-move": "{tilde}", "ajv": "{deps["node/la/package.json"]}"}}}}\n'
            ),
            "node/package-lock.json": (
                f'{{"name": "workspace", "lockfileVersion": 3, "packages": {{'
                f'"": {{"name": "workspace", "workspaces": ["trmv", "la"]}}, '
                f'"trmv": {{"name": "type-rename-move", "version": "{version}"}}, '
                f'"la": {{"name": "living-architecture", "version": "{version}",'
                f' "dependencies": {{"type-rename-move": "{tilde}"}}}}, '
                f'"node_modules/ajv": {{"version": "{deps["node/package-lock.json"]}"}}}}}}\n'
            ),
            "plugin/trmv/.claude-plugin/plugin.json": f'{{"name": "trmv", "version": "{version}"}}\n',
            "plugin/la/.claude-plugin/plugin.json": (
                f'{{"name": "la", "version": "{version}", "dependencies": [{{"name": "trmv", "version": "{tilde}"}}]}}\n'
            ),
        }

    def bump(self, version: str) -> None:
        """Commit every manifest and lockfile at `version`, snapshot hashes synced, then `overrides` on top."""
        for rel, text in self.manifests(version).items():
            self.write(rel, text)
        for rel, package in RELEASE_SNAPSHOTS.items():
            self.write(rel, compute_hash(self.root / "shared" / package) + "\n")
        for rel, text in self.overrides.items():
            self.write(rel, text)
        self.commit(f"release {version}")

    def tag(self, name: str, *, annotated: bool = False) -> None:
        self.git("tag", *(["-a", "-m", name] if annotated else []), name)

    def release(self, version: str, *, annotated: bool = False, plugin_tag: bool = True) -> None:
        """Bump and tag `version`, and its trmv plugin tag at the same commit unless `plugin_tag` is False."""
        self.bump(version)
        self.tag(f"v{version}", annotated=annotated)
        if plugin_tag:
            self.tag(f"trmv--v{version}")

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
