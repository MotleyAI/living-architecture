"""The publish workflow builds both packages and publishes dr before la on each registry, after the release check."""

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
    published = [step["with"]["packages-dir"] for step in steps if "pypi-publish" in step.get("uses", "")]
    assert published == ["python/dist/dr/", "python/dist/la/"]


def test_npm_publishes_dr_before_la() -> None:
    [publish] = [step["run"] for step in _jobs()["npm"]["steps"] if "npm publish" in step.get("run", "")]
    assert "for package in dr la;" in publish
    assert 'npm publish -w "$package" --provenance --access public' in publish
