"""Each package's built wheel and sdist carry its README and the root LICENSE, its contract, and trmv's pyright preloads."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path, PurePosixPath

import pytest

from trmv.config import current_format
from trmv.contract import compute_hash


def _repo_root() -> Path:
    return next(p for p in Path(__file__).resolve().parents if (p / "shared").is_dir() and (p / "plugin").is_dir())


REPO_ROOT = _repo_root()
WORKSPACE = REPO_ROOT / "python"
FIXTURES = REPO_ROOT / "conformance" / "fixtures"
CLEAN = '"""Clean."""\n\nimport os\n\n\ndef f(x: int) -> str:\n    return os.sep * x\n'
PACKAGES = {"trmv": "type-rename-move", "la": "living-architecture"}
# The README each package's listing carries: trmv has its own, la the repo's.
READMES = {"trmv": WORKSPACE / "trmv" / "README.md", "la": REPO_ROOT / "README.md"}


@pytest.fixture(scope="module")
def artifacts(tmp_path_factory: pytest.TempPathFactory) -> dict[str, dict[str, Path]]:
    """Per package, its wheel and sdist."""
    dist = tmp_path_factory.mktemp("dist")
    for name in PACKAGES.values():
        subprocess.run(["uv", "build", "--package", name, "--out-dir", str(dist)], cwd=WORKSPACE, check=True,
                       capture_output=True)
    built = {}
    for package, name in PACKAGES.items():
        stem = name.replace("-", "_")
        [wheel] = dist.glob(f"{stem}-*.whl")
        [sdist] = dist.glob(f"{stem}-*.tar.gz")
        built[package] = {"wheel": wheel, "sdist": sdist}
    return built


def _root_file(package: str, name: str) -> Path:
    return READMES[package] if name == "README.md" else REPO_ROOT / name


@pytest.mark.parametrize("package", PACKAGES)
@pytest.mark.parametrize("name", ["README.md", "LICENSE"])
def test_sdist_carries_the_root_file(artifacts, package, name):
    with tarfile.open(artifacts[package]["sdist"]) as sdist:
        [member] = [m for m in sdist.getmembers() if PurePosixPath(m.name).parts[1:] == (name,)]
        assert member.isfile(), member.type
        extracted = sdist.extractfile(member)
        assert extracted is not None
        assert extracted.read() == _root_file(package, name).read_bytes()


def _wheel_file(wheel: Path, suffix: str) -> bytes:
    with zipfile.ZipFile(wheel) as archive:
        [name] = [n for n in archive.namelist() if n.endswith(suffix)]
        return archive.read(name)


@pytest.mark.parametrize("package", PACKAGES)
def test_wheel_description_is_the_package_readme(artifacts, package):
    metadata = _wheel_file(artifacts[package]["wheel"], ".dist-info/METADATA").decode("utf-8")
    _, _, description = metadata.partition("\n\n")
    assert description == READMES[package].read_text(encoding="utf-8")


@pytest.mark.parametrize("package", PACKAGES)
def test_wheel_license_is_the_root_license(artifacts, package):
    assert _wheel_file(artifacts[package]["wheel"], ".dist-info/licenses/LICENSE") == (REPO_ROOT / "LICENSE").read_bytes()


def _install(where: Path, *artifacts: Path) -> Path:
    venv = where / "venv"
    subprocess.run(["uv", "venv", "--python", sys.executable, str(venv)], check=True, capture_output=True)
    subprocess.run(["uv", "pip", "install", "--python", str(venv / "bin" / "python"), *map(str, artifacts)],
                   check=True, capture_output=True)
    return venv / "bin"


def _materialize(fixture: str, dest: Path) -> Path:
    for overlay in ("repo", "python"):
        shutil.copytree(FIXTURES / fixture / overlay, dest, dirs_exist_ok=True)
    return dest


@pytest.mark.parametrize("kind", ["wheel", "sdist"])
def test_installed_artifact_runs_every_command(kind, artifacts, tmp_path, fake_gh):
    bin_dir = _install(tmp_path, artifacts["trmv"][kind], artifacts["la"][kind])
    work = tmp_path / "work"
    work.mkdir()
    (work / "a.py").write_text(CLEAN, encoding="utf-8")
    env = {**fake_gh.env(), "PATH": os.pathsep.join([str(fake_gh.bin), str(bin_dir), os.environ["PATH"]])}
    fake_gh.route((["repos/o/r/pulls/3/comments/9/replies"], {"html_url": "u"}),
                  (["pr", "view", "headRefOid,mergeable,statusCheckRollup"],
                   {"headRefOid": "abc", "mergeable": "MERGEABLE", "statusCheckRollup": []}),
                  (["api", "user"], {"login": "me"}),
                  (["repos/o/r/commits/abc/check-suites"], {"check_suites": []}),
                  (["repos/o/r/issues/7/comments"], []),
                  (["repos/o/r/pulls/7/reviews"], []),
                  (["repos/o/r/pulls/7/comments"], []))
    scaffold = tmp_path / "scaffold"
    (scaffold / "architecture").mkdir(parents=True)
    (scaffold / "architecture" / "index.yaml").write_text("python:\n  root_package: pkg\n", encoding="utf-8")
    for module in ("pkg/__init__.py", "pkg/a/__init__.py", "pkg/b.py"):
        (scaffold / module).parent.mkdir(parents=True, exist_ok=True)
        (scaffold / module).write_text("from pkg import b\n" if module.startswith("pkg/a") else "", encoding="utf-8")
    legacy = tmp_path / "legacy"
    (legacy / "architecture" / "model").mkdir(parents=True)
    (legacy / "architecture" / "model" / "m.c4").write_text("specification {\n}\nmodel {\n}\n", encoding="utf-8")
    (legacy / "living-architecture.yaml").write_text("tracker: linear\n", encoding="utf-8")

    def run(*argv: str, stdin: str = "") -> subprocess.CompletedProcess[str]:
        return subprocess.run([str(bin_dir / argv[0]), *argv[1:]], cwd=work, env=env, input=stdin,
                              capture_output=True, text=True, timeout=120, check=False)

    expectations = [
        (("trmv-doctor", "--contract-hash"), 0, f"{compute_hash(REPO_ROOT / 'shared' / 'trmv')}\n"),
        (("la-doctor", "--contract-hash"), 0, f"{compute_hash(REPO_ROOT / 'shared' / 'la')}\n"),
        (("trmv-config", "show"), 0, None),
        (("la-config", "show"), 0, None),
        (("la-arch-check", "--root", str(_materialize("arch-ok", tmp_path / "arch"))), 0, "arch_check: OK\n"),
        (("la-arch-diagrams", "--root", str(_materialize("arch-diagrams", tmp_path / "diagrams"))), 0, ""),
        (("la-check-conventions", "--file", "a.py"), 0, None),
        (("la-count-comments", "a.py"), 0, None),
        (("trmv-typecheck",), 2, ""),
        (("la-typecheck",), 2, ""),
        (("trmv-compliance", "a.py"), 0, ""),
        (("trmv-mock-lint", "a.py"), 0, ""),
        (("trmv-refactor", "--help"), 0, None),
        (("la-reply-to-pr-thread", "--comment-id", "9", "--pr", "3", "--repo", "o/r"), 0, "u\n"),
        (("la-wait-for-reviews", "7", "--repo", "o/r"), 0, None),
        (("la-pr-reviewers", "7", "--repo", "o/r"), 0,
         '{"coderabbit":false,"sonar":{"present":false,"project_key":null}}\n'),
        (("la-arch-scaffold", "--root", str(scaffold)), 0, None),
        (("la-arch-migrate", "--root", str(legacy)), 0, None),
    ]
    for argv, code, stdout in expectations:
        proc = run(*argv, stdin="body")
        assert proc.returncode == code, (argv, proc.stdout, proc.stderr)
        if stdout is not None:
            assert proc.stdout == stdout, argv
    assert "    a -> b\n" in (scaffold / "architecture" / "model.c4").read_text(encoding="utf-8")
    assert (legacy / "architecture" / "model.c4").read_text(encoding="utf-8") == "specification {\n}\nmodel {\n}\n"
    assert (legacy / "living-architecture.yaml").read_text(encoding="utf-8") == f"format: {current_format('living-architecture.yaml')}\ntracker: linear\n"


@pytest.mark.parametrize(("source", "attribute"), [
    ("pyright_patch.cjs", "PYRIGHT_PATCH_PRELOAD"),
    ("pyright_export.cjs", "PYRIGHT_EXPORT_PRELOAD"),
])
def test_trmv_wheel_carries_the_pyright_preload(artifacts, tmp_path, source, attribute):
    expected = (WORKSPACE / "trmv" / "src" / "trmv" / "lang" / source).read_bytes()
    assert _wheel_file(artifacts["trmv"]["wheel"], f"trmv/lang/{source}") == expected
    bin_dir = _install(tmp_path, artifacts["trmv"]["wheel"])
    located = subprocess.run(
        [str(bin_dir / "python"), "-c", f"from trmv import lang; print(lang.{attribute})"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    assert Path(located).is_relative_to(tmp_path / "venv")
    assert Path(located).read_bytes() == expected
