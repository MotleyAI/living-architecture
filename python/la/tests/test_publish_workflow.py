"""The publish workflow builds both packages and publishes dr before la on each registry, after the release check."""

import json
import subprocess
from pathlib import Path

import pytest
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


# What the fake npm's `view` of living-architecture@1.2.0 prints to stdout and stderr, and its exit code.
LA_UNPUBLISHED_VERSION = ("", "", 0)
LA_UNPUBLISHED_PACKAGE = ("", "npm error code E404", 1)
LA_LOOKUP_DENIED = ("", "npm error code E401", 1)


def _publish(tmp_path: Path, la_view: tuple[str, str, int]) -> tuple[int, list[str]]:
    """Run the npm publish step where deterministic-refactor@1.2.0 is on npm; its exit code and the publishes it ran."""
    [publish] = [step["run"] for step in _jobs()["npm"]["steps"] if "npm publish" in step.get("run", "")]
    for package, name in (("dr", "deterministic-refactor"), ("la", "living-architecture")):
        (tmp_path / package).mkdir()
        (tmp_path / package / "package.json").write_text(json.dumps({"name": name, "version": "1.2.0"}))
    fake = tmp_path / "bin"
    fake.mkdir()
    out, err, code = la_view
    (fake / "npm").write_text(
        "#!/bin/sh\n"
        'if [ "$1 $2" = "view deterministic-refactor@1.2.0" ]; then echo 1.2.0; exit 0; fi\n'
        f'if [ "$1" = view ]; then printf %s "{out}"; printf %s "{err}" >&2; exit {code}; fi\n'
        'echo "$*" >> "$NPM_LOG"\n'
    )
    (fake / "npm").chmod(0o755)
    log = tmp_path / "npm.log"
    env = {"PATH": f"{fake}:/usr/bin:/bin", "NPM_LOG": str(log)}
    proc = subprocess.run(["bash", "-e", "-c", publish], cwd=tmp_path, env=env, capture_output=True, check=False)
    return proc.returncode, log.read_text().splitlines() if log.exists() else []


@pytest.mark.parametrize("la_view", [LA_UNPUBLISHED_VERSION, LA_UNPUBLISHED_PACKAGE])
def test_npm_rerun_publishes_only_the_missing_package(tmp_path: Path, la_view: tuple[str, str, int]) -> None:
    assert _publish(tmp_path, la_view) == (0, ["publish -w la --provenance --access public"])


def test_npm_lookup_failure_stops_the_publish(tmp_path: Path) -> None:
    code, published = _publish(tmp_path, LA_LOOKUP_DENIED)
    assert code != 0
    assert published == []
