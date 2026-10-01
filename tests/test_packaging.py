"""The built wheel and sdist carry the contract when installed outside the checkout."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from living_architecture.contract import compute_hash


def _repo_root() -> Path:
    return next(p for p in Path(__file__).resolve().parents if (p / "conformance" / "cases").is_dir())


REPO_ROOT = _repo_root()
PROJECT = REPO_ROOT / "python"
FIXTURES = REPO_ROOT / "conformance" / "fixtures"
CLEAN = '"""Clean."""\n\nimport os\n\n\ndef f(x: int) -> str:\n    return os.sep * x\n'


@pytest.fixture(scope="module")
def artifacts(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    dist = tmp_path_factory.mktemp("dist")
    subprocess.run(["uv", "build", "--out-dir", str(dist), str(PROJECT)], check=True, capture_output=True)
    [wheel] = dist.glob("*.whl")
    [sdist] = dist.glob("*.tar.gz")
    return {"wheel": wheel, "sdist": sdist}


def _install(artifact: Path, where: Path) -> Path:
    venv = where / "venv"
    subprocess.run(["uv", "venv", "--python", sys.executable, str(venv)], check=True, capture_output=True)
    subprocess.run(["uv", "pip", "install", "--python", str(venv / "bin" / "python"), str(artifact)],
                   check=True, capture_output=True)
    return venv / "bin"


def _materialize(fixture: str, dest: Path) -> Path:
    for overlay in ("repo", "python"):
        shutil.copytree(FIXTURES / fixture / overlay, dest, dirs_exist_ok=True)
    return dest


@pytest.mark.parametrize("kind", ["wheel", "sdist"])
def test_installed_artifact_runs_every_command(kind, artifacts, tmp_path, fake_gh):
    bin_dir = _install(artifacts[kind], tmp_path)
    work = tmp_path / "work"
    work.mkdir()
    (work / "a.py").write_text(CLEAN, encoding="utf-8")
    env = {**fake_gh.env(), "PATH": os.pathsep.join([str(fake_gh.bin), str(bin_dir), os.environ["PATH"]])}
    fake_gh.route((["repos/o/r/pulls/3/comments/9/replies"], {"html_url": "u"}),
                  (["pr", "view", "statusCheckRollup"], {"statusCheckRollup": []}))

    def run(*argv: str, stdin: str = "") -> subprocess.CompletedProcess[str]:
        return subprocess.run([str(bin_dir / argv[0]), *argv[1:]], cwd=work, env=env, input=stdin,
                              capture_output=True, text=True, check=False)

    expectations = [
        (("la-doctor", "--contract-hash"), 0, f"{compute_hash(REPO_ROOT / 'shared')}\n"),
        (("la-config", "show"), 0, None),
        (("la-arch-check", "--root", str(_materialize("arch-ok", tmp_path / "arch"))), 0, "arch_check: OK\n"),
        (("la-arch-diagrams", "--root", str(_materialize("arch-diagrams", tmp_path / "diagrams"))), 0, ""),
        (("la-check-conventions", "--file", "a.py"), 0, None),
        (("la-count-comments", "a.py"), 0, None),
        (("dr-compliance", "a.py"), 0, ""),
        (("dr-mock-lint", "a.py"), 0, ""),
        (("dr-refactor", "--help"), 0, None),
        (("la-reply-to-pr-thread", "--comment-id", "9", "--pr", "3", "--repo", "o/r"), 0, "u\n"),
        (("la-wait-for-reviews", "7", "--repo", "o/r"), 0, None),
    ]
    for argv, code, stdout in expectations:
        proc = run(*argv, stdin="body")
        assert proc.returncode == code, (argv, proc.stdout, proc.stderr)
        if stdout is not None:
            assert proc.stdout == stdout, argv
