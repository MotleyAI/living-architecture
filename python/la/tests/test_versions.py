import importlib.util
import json
import os
import re
import subprocess
import tomllib
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from deterministic_refactor import config
from living_architecture import __version__

REPO_ROOT = next(p for p in Path(__file__).resolve().parents if (p / "shared").is_dir() and (p / "plugin").is_dir())
PACKAGES = ("dr", "la")
# An install pin: `<package>==X` (PyPI) or `<package>@X` (npm).
PIN = re.compile(r"(?:living-architecture|deterministic-refactor)(?:==|@)(\d[\w.+-]*)")
# A tool input of the release rule.
TOOL = "python/la/src/living_architecture/__init__.py"


def _json(rel: str) -> dict:
    return json.loads((REPO_ROOT / rel).read_text(encoding="utf-8"))


def _plugin(package: str) -> dict:
    return _json(f"plugin/{package}/.claude-plugin/plugin.json")


def _marketplace_entry(package: str) -> dict:
    return next(entry for entry in _json(".claude-plugin/marketplace.json")["plugins"] if entry["name"] == package)


def _npm_package(package: str) -> dict:
    return _json(f"node/{package}/package.json")


def _pyproject(package: str) -> dict:
    return tomllib.loads((REPO_ROOT / "python" / package / "pyproject.toml").read_text(encoding="utf-8"))["project"]


@pytest.mark.parametrize(
    ("package", "name"), [("la", "README.md"), ("la", "LICENSE"), ("dr", "LICENSE")], ids=lambda v: v
)
def test_root_files_are_relative_symlinks(package: str, name: str) -> None:
    link = REPO_ROOT / "python" / package / name
    assert link.is_symlink(), f"python/{package}/{name} is not a symlink"
    assert os.readlink(link) == f"../../{name}"
    assert link.resolve() == (REPO_ROOT / name).resolve()


@pytest.mark.parametrize("package", PACKAGES)
def test_package_listings_share_one_description(package: str) -> None:
    descriptions = {_pyproject(package)["description"], _npm_package(package)["description"], _plugin(package)["description"]}
    assert descriptions == {_marketplace_entry(package)["description"]}


@pytest.mark.parametrize("package", PACKAGES)
def test_package_listings_share_the_keywords(package: str) -> None:
    keywords = _pyproject(package)["keywords"]
    assert keywords
    assert _npm_package(package)["keywords"] == _plugin(package)["keywords"] == keywords


@pytest.mark.parametrize("package", PACKAGES)
def test_pypi_links_back_to_the_repo(package: str) -> None:
    urls = _pyproject(package)["urls"]
    assert urls["Repository"] == "https://github.com/MotleyAI/living-architecture"
    assert all(url.startswith(urls["Repository"]) for url in urls.values())


@pytest.mark.parametrize("package", PACKAGES)
def test_python_classifiers_match_the_ci_matrix(package: str) -> None:
    ci = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    matrix = re.search(r"python-version: \[([^\]]*)\]", ci)
    assert matrix
    tested = [version.strip().strip('"') for version in matrix.group(1).split(",")]
    prefix = "Programming Language :: Python :: "
    declared = [c.removeprefix(prefix) for c in _pyproject(package)["classifiers"] if c.startswith(prefix + "3.")]
    assert declared == tested


def test_doc_pins_name_the_current_version() -> None:
    docs = [REPO_ROOT / "README.md", *sorted((REPO_ROOT / "docs").glob("*.md"))]
    pins = [(doc.name, version) for doc in docs for version in PIN.findall(doc.read_text(encoding="utf-8"))]
    assert pins, "no package version pin found in README.md or docs/"
    assert [pin for pin in pins if pin[1] != __version__] == []


def test_current_format_is_at_most_every_package_version() -> None:
    """The format is the version of the release that introduced it, so it never runs ahead of a package."""
    versions = [
        *(_pyproject(package)["version"] for package in PACKAGES),
        *(_npm_package(package)["version"] for package in PACKAGES),
        *(_plugin(package)["version"] for package in PACKAGES),
    ]
    for name in ("living-architecture.yaml", "deterministic-refactor.yaml"):
        current = config.released_formats(name)[-1]
        assert current == config.current_format(name)
        for version in versions:
            assert config.compare_versions(current, version) <= 0, (name, version)


@pytest.fixture(scope="session")
def release_rule() -> ModuleType:
    """scripts/release_rule.py, the release rule `scripts/release-check` applies."""
    spec = importlib.util.spec_from_file_location("release_rule", REPO_ROOT / "scripts" / "release_rule.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _unreleased_bump_problem(root: Path, version: str, rule: ModuleType, *, on_actions: bool) -> str | None:
    """The release rule's problem with `version` while it has no tag; skips (fails on Actions) without a release tag."""
    tagged = subprocess.run(
        ["git", "rev-parse", "-q", "--verify", f"refs/tags/v{version}"], cwd=root, capture_output=True, check=False
    )
    if tagged.returncode == 0:
        return None
    previous = rule.previous_release(root, version)
    if previous is None:
        reason = f"no release tag below {version} is reachable; fetch the full history with tags"
        if on_actions:
            pytest.fail(reason)
        pytest.skip(reason)
    return rule.bump_problem(root, version, previous)


def test_an_unreleased_version_obeys_the_release_rule(release_rule: ModuleType) -> None:
    on_actions = os.environ.get("GITHUB_ACTIONS") == "true"
    assert _unreleased_bump_problem(REPO_ROOT, __version__, release_rule, on_actions=on_actions) is None



def test_the_rule_is_not_applied_once_the_version_is_tagged(release_repo, release_rule: ModuleType) -> None:
    release_repo.release("0.4.0")
    release_repo.change(TOOL)
    release_repo.release("0.4.1")
    assert _unreleased_bump_problem(release_repo.root, "0.4.1", release_rule, on_actions=True) is None


def test_a_tool_change_without_a_minor_bump_fails_before_tagging(release_repo, release_rule: ModuleType) -> None:
    release_repo.release("0.4.0")
    release_repo.change(TOOL)
    release_repo.bump("0.4.1")
    problem = _unreleased_bump_problem(release_repo.root, "0.4.1", release_rule, on_actions=False)
    assert problem is not None
    assert "v0.4.0" in problem
    assert TOOL in problem


def test_a_tool_change_with_a_minor_bump_passes_before_tagging(release_repo, release_rule: ModuleType) -> None:
    release_repo.release("0.4.0")
    release_repo.change(TOOL)
    release_repo.bump("0.5.0")
    assert _unreleased_bump_problem(release_repo.root, "0.5.0", release_rule, on_actions=False) is None


def test_no_release_tag_skips_locally(release_repo, release_rule: ModuleType) -> None:
    release_repo.bump("0.4.1")
    with pytest.raises(pytest.skip.Exception):
        _unreleased_bump_problem(release_repo.root, "0.4.1", release_rule, on_actions=False)


def test_no_release_tag_fails_on_github_actions(release_repo, release_rule: ModuleType) -> None:
    release_repo.bump("0.4.1")
    with pytest.raises(pytest.fail.Exception):
        _unreleased_bump_problem(release_repo.root, "0.4.1", release_rule, on_actions=True)


FORMATS_CONFIG = "shared/dr/config.yaml"


def _formats(la: str) -> str:
    return f"files: [living-architecture.yaml]\nformats:\n  living-architecture.yaml: {la}\n"


@pytest.mark.parametrize(
    ("text", "formats"),
    [
        ("formats: [0.4.0]\n", ["0.4.0"]),
        ("formats: [0.4.0, 0.7.0]\n", ["0.4.0", "0.7.0"]),
        ("# released\nfile: x\nformats: [0.4.0, 0.7.0]  # oldest first\r\n", ["0.4.0", "0.7.0"]),
        ("format: 0.4.0\n", ["0.4.0"]),
        ("format: '0.4.0'\n", ["0.4.0"]),
        ('format: "0.4.0"\n', ["0.4.0"]),
        ("format: 0.4.0\r\nfile: x\r\n", ["0.4.0"]),
        ("# The repo format.\nfile: x\nformat: 0.4.0  # current\nlocal_file: y\n", ["0.4.0"]),
        ("file: x\n", None),
        ("formats:\n- 0.4.0\n", None),
        ("format: [0.4.0]\n", None),
        ("format: 0.4\n", None),
        ("formats: [0.4]\n", None),
    ],
    ids=["one", "two", "comments-crlf", "single", "single-quoted", "double-quoted", "single-crlf",
         "single-comments", "neither", "block-list", "format-list", "invalid", "invalid-entry"],
)
def test_the_formats_reader(release_rule: ModuleType, text: str, formats: list[str] | None) -> None:
    assert release_rule.parse_formats(text) == formats


@pytest.mark.parametrize(
    ("text", "formats"),
    [
        ("formats:\n  a.yaml: [0.4.0]\n  b.yaml: [0.4.0, 0.7.0]  # oldest first\r\nnext: x\n",
         {"a.yaml": ["0.4.0"], "b.yaml": ["0.4.0", "0.7.0"]}),
        ("formats:  # per file\n  a.yaml: []\n", {"a.yaml": []}),
        ("formats: [0.4.0]\n", None),
        ("formats:\n  a.yaml: 0.4.0\n", None),
        ("formats:\n  a.yaml: [0.4]\n", None),
        ("formats:\n  a.yaml: [0.4.0]\n  a.yaml: [0.7.0]\n", None),
        ("formats:\nnext: x\n", None),
        ("file: x\n", None),
    ],
    ids=["two-files", "empty-list", "one-list", "scalar", "invalid-entry", "duplicate", "empty-block", "neither"],
)
def test_the_per_file_formats_reader(release_rule: ModuleType, text: str, formats: dict[str, list[str]] | None) -> None:
    assert release_rule.parse_file_formats(text) == formats


def test_formats_appending_another_version_fail_before_tagging(release_repo, release_rule: ModuleType) -> None:
    release_repo.write(FORMATS_CONFIG, _formats("[0.4.0]"))
    release_repo.release("0.6.0")
    release_repo.write(FORMATS_CONFIG, _formats("[0.4.0, 0.8.0]"))
    release_repo.bump("0.7.0")
    problem = _unreleased_bump_problem(release_repo.root, "0.7.0", release_rule, on_actions=False)
    assert problem is not None
    assert all(needle in problem for needle in ("[0.4.0]", "[0.4.0, 0.8.0]", "0.7.0")), problem


def test_formats_appending_the_own_version_pass_before_tagging(release_repo, release_rule: ModuleType) -> None:
    release_repo.write(FORMATS_CONFIG, _formats("[0.4.0]"))
    release_repo.release("0.6.0")
    release_repo.write(FORMATS_CONFIG, _formats("[0.4.0, 0.7.0]"))
    release_repo.bump("0.7.0")
    assert _unreleased_bump_problem(release_repo.root, "0.7.0", release_rule, on_actions=False) is None


def test_a_formats_change_fails_even_with_a_minor_bump_and_no_other_change(release_repo, release_rule: ModuleType) -> None:
    release_repo.write(FORMATS_CONFIG, _formats("[0.4.0]"))
    release_repo.release("0.6.0")
    release_repo.write(FORMATS_CONFIG, _formats("[0.4.1]"))
    release_repo.bump("0.7.0")
    problem = _unreleased_bump_problem(release_repo.root, "0.7.0", release_rule, on_actions=False)
    assert problem is not None
    assert "[0.4.1]" in problem, problem


def test_an_unreadable_previous_formats_list_fails_naming_the_release(
    release_repo, release_rule: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    release_repo.release("0.6.0")
    release_repo.bump("0.7.0")
    real = subprocess.run

    def failing_show(args: Any, *rest: Any, **kwargs: Any) -> Any:
        if list(args[:2]) == ["git", "show"] and str(args[2]) == f"v0.6.0:{FORMATS_CONFIG}":
            if kwargs.get("check"):
                raise subprocess.CalledProcessError(128, args, "", "fatal: bad object")
            return subprocess.CompletedProcess(args, 128, "", "fatal: bad object")
        return real(args, *rest, **kwargs)

    monkeypatch.setattr(release_rule.subprocess, "run", failing_show)
    problem = release_rule.bump_problem(release_repo.root, "0.7.0", "v0.6.0")
    assert problem is not None
    assert "v0.6.0" in problem, problem
