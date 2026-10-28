"""scripts/release-check: versions equal the tag, contract hashes agree, and a tool change raises the minor version."""

import subprocess

import pytest

TOOL = "python/src/living_architecture/__init__.py"
MANIFESTS = ["python/pyproject.toml", "python/uv.lock", "node/package.json", "node/package-lock.json"]


def _accepted(proc: subprocess.CompletedProcess[str]) -> None:
    assert proc.returncode == 0, proc.stderr


def _refused(proc: subprocess.CompletedProcess[str], *needles: str) -> None:
    assert proc.returncode == 1, proc.stderr
    for needle in needles:
        assert needle in proc.stderr


def test_a_release_history(release_repo) -> None:
    release_repo.release("0.4.0")
    release_repo.change(TOOL)
    release_repo.release("0.5.0")
    _accepted(release_repo.release_check("v0.5.0"))
    release_repo.change("docs/index.md")
    release_repo.release("0.5.1")
    _accepted(release_repo.release_check("v0.5.1"))
    release_repo.change("node/src/index.ts")
    release_repo.release("0.5.2")
    _refused(release_repo.release_check("v0.5.2"), "v0.5.1", "node/src/index.ts")


def test_plugin_docs_and_tests_only_patch_is_accepted(release_repo) -> None:
    release_repo.release("0.4.0")
    for rel in ("plugin/skills/pr/SKILL.md", "docs/index.md", "python/tests/test_x.py", "README.md"):
        release_repo.change(rel)
    release_repo.release("0.4.1")
    _accepted(release_repo.release_check("v0.4.1"))


def test_version_only_manifest_changes_do_not_count(release_repo) -> None:
    release_repo.release("0.4.0")
    release_repo.release("0.4.1")
    assert set(release_repo.git("diff", "--name-only", "v0.4.0", "v0.4.1").split()) == {
        *MANIFESTS, "plugin/.claude-plugin/plugin.json"
    }
    _accepted(release_repo.release_check("v0.4.1"))


@pytest.mark.parametrize(
    "rel",
    [
        "shared/cli.yaml",
        "shared/new.yaml",
        "conformance/README.md",
        TOOL,
        "node/src/index.ts",
        "node/scripts/build.mjs",
        "node/tsconfig.json",
        "node/tsconfig.build.json",
    ],
)
def test_each_tool_input_counts(release_repo, rel: str) -> None:
    release_repo.release("0.4.0")
    release_repo.change(rel)
    release_repo.release("0.4.1")
    _refused(release_repo.release_check("v0.4.1"), "v0.4.0", rel)


def test_a_deleted_tool_input_counts(release_repo) -> None:
    release_repo.release("0.4.0")
    (release_repo.root / "node" / "scripts" / "build.mjs").unlink()
    release_repo.release("0.4.1")
    _refused(release_repo.release_check("v0.4.1"), "v0.4.0", "node/scripts/build.mjs")


@pytest.mark.parametrize("manifest", MANIFESTS)
def test_a_dependency_change_counts(release_repo, manifest: str) -> None:
    release_repo.release("0.4.0")
    release_repo.deps[manifest] = "9.9.9"
    release_repo.release("0.4.1")
    _refused(release_repo.release_check("v0.4.1"), "v0.4.0", manifest)


def test_a_major_bump_is_accepted(release_repo) -> None:
    release_repo.release("0.4.0")
    release_repo.change(TOOL)
    release_repo.release("1.0.0")
    _accepted(release_repo.release_check("v1.0.0"))


def test_the_previous_release_is_chosen_numerically(release_repo) -> None:
    release_repo.release("0.9.0")
    release_repo.change(TOOL)
    release_repo.release("0.10.0")
    release_repo.release("0.10.1")
    _accepted(release_repo.release_check("v0.10.1"))
    release_repo.change(TOOL)
    release_repo.release("0.10.2")
    proc = release_repo.release_check("v0.10.2")
    _refused(proc, "v0.10.1")
    assert "v0.9.0" not in proc.stderr


def test_other_tag_forms_are_ignored(release_repo) -> None:
    release_repo.release("0.4.0")
    release_repo.change(TOOL)
    release_repo.commit()
    for name in ("v0.4.1-rc1", "other", "v0.4"):
        release_repo.tag(name)
    release_repo.release("0.4.1")
    _refused(release_repo.release_check("v0.4.1"), "v0.4.0", TOOL)


def test_unreachable_tags_are_ignored(release_repo) -> None:
    release_repo.release("0.4.0")
    release_repo.git("checkout", "-q", "-b", "side")
    release_repo.change(TOOL)
    release_repo.release("0.4.5")
    release_repo.git("checkout", "-q", "main")
    release_repo.change(TOOL)
    release_repo.release("0.4.6")
    _refused(release_repo.release_check("v0.4.6"), "v0.4.0", TOOL)


def test_a_shallow_clone_is_refused(release_repo) -> None:
    release_repo.release("0.4.0")
    release_repo.change(TOOL)
    release_repo.release("0.5.0")
    _refused(release_repo.release_check("v0.5.0", root=release_repo.shallow_clone("v0.5.0")), "shallow")


def test_no_reachable_previous_release_is_refused(release_repo) -> None:
    release_repo.release("0.4.0")
    _refused(release_repo.release_check("v0.4.0"), "no previous release")


@pytest.mark.parametrize("annotated", [False, True], ids=["lightweight", "annotated"])
def test_head_must_be_the_tagged_commit(release_repo, annotated: bool) -> None:
    release_repo.release("0.4.0")
    release_repo.change(TOOL)
    release_repo.release("0.5.0", annotated=annotated)
    _accepted(release_repo.release_check("v0.5.0"))
    release_repo.change("docs/index.md")
    release_repo.commit()
    _refused(release_repo.release_check("v0.5.0"), "HEAD")


def test_a_version_other_than_the_tag_is_refused(release_repo) -> None:
    release_repo.release("0.4.0")
    release_repo.change(TOOL)
    release_repo.release("0.5.0", plugin="0.5.9")
    _refused(release_repo.release_check("v0.5.0"), "plugin/.claude-plugin/plugin.json is 0.5.9")


def test_differing_contract_hashes_are_refused(release_repo) -> None:
    release_repo.release("0.4.0")
    release_repo.change(TOOL)
    release_repo.write("node/src/contract/data/CONTRACT_HASH", "other\n")
    release_repo.release("0.5.0")
    _refused(release_repo.release_check("v0.5.0"), "contract hashes differ")
