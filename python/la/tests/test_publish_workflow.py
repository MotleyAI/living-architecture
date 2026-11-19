"""The publish workflow builds both packages and publishes dr before la on each registry, after the release check."""

import json
import subprocess
from pathlib import Path

import yaml

REPO_ROOT = next(p for p in Path(__file__).resolve().parents if (p / "shared").is_dir() and (p / "plugin").is_dir())
PUBLISH = REPO_ROOT / ".github" / "workflows" / "publish.yml"


def _jobs() -> dict:
    return yaml.safe_load(PUBLISH.read_text(encoding="utf-8"))["jobs"]


def test_registries_publish_only_after_the_release_check() -> None:
    jobs = _jobs()
    assert any("scripts/release-check" in step.get("run", "") for step in jobs["check"]["steps"])
    assert jobs["pypi"]["needs"] == jobs["npm"]["needs"] == "check"


def test_pypi_publishes_dr_before_la() -> None:
    steps = _jobs()["pypi"]["steps"]
    builds = [step["run"] for step in steps if step.get("run", "").startswith("uv build")]
    assert builds == [
        "uv build --package deterministic-refactor --out-dir dist/dr",
        "uv build --package living-architecture --out-dir dist/la",
    ]
    published = [step["with"] for step in steps if "pypi-publish" in step.get("uses", "")]
    assert [options["packages-dir"] for options in published] == ["python/dist/dr/", "python/dist/la/"]
    assert all(options["skip-existing"] is True for options in published)


def test_npm_publishes_dr_before_la() -> None:
    [publish] = [step["run"] for step in _jobs()["npm"]["steps"] if "npm publish" in step.get("run", "")]
    assert "for package in dr la;" in publish
    assert 'npm publish -w "$package" --provenance --access public' in publish


def test_npm_installs_run_no_lifecycle_scripts() -> None:
    runs = [step.get("run", "").split() for step in _jobs()["npm"]["steps"]]
    installs = [tokens for tokens in runs if tokens[:2] in (["npm", "ci"], ["npm", "install"])]
    assert len(installs) == 2
    assert all("--ignore-scripts" in tokens for tokens in installs), installs


def test_npm_rerun_publishes_only_the_missing_package(tmp_path: Path) -> None:
    [publish] = [step["run"] for step in _jobs()["npm"]["steps"] if "npm publish" in step.get("run", "")]
    for package, name in (("dr", "deterministic-refactor"), ("la", "living-architecture")):
        (tmp_path / package).mkdir()
        (tmp_path / package / "package.json").write_text(json.dumps({"name": name, "version": "1.2.0"}))
    fake = tmp_path / "bin"
    fake.mkdir()
    # npm knows deterministic-refactor@1.2.0 only, and logs every publish.
    (fake / "npm").write_text(
        '#!/bin/sh\n'
        'if [ "$1" = view ]; then [ "$2" = deterministic-refactor@1.2.0 ] && echo 1.2.0; exit 0; fi\n'
        'echo "$*" >> "$NPM_LOG"\n'
    )
    (fake / "npm").chmod(0o755)
    log = tmp_path / "npm.log"
    env = {"PATH": f"{fake}:/usr/bin:/bin", "NPM_LOG": str(log)}
    subprocess.run(["bash", "-e", "-c", publish], cwd=tmp_path, env=env, check=True, capture_output=True)
    assert log.read_text().splitlines() == ["publish -w la --provenance --access public"]
