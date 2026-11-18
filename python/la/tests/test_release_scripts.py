"""scripts/release-check: versions equal the tag, contract hashes agree, and a tool change raises the minor version."""

import subprocess

import pytest

TOOL = "python/src/living_architecture/__init__.py"
MANIFESTS = ["python/pyproject.toml", "python/uv.lock", "node/package.json", "node/package-lock.json"]


def _accepted(proc: subprocess.CompletedProcess[str]) -> None:
    assert proc.returncode == 0, proc.stderr


def _pinned(manifest: str, version: str) -> str:
    """A dependency spec pinning `version` in `manifest`."""
    return f"=={version}" if manifest.endswith(".toml") else version


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


@pytest.mark.parametrize("manifest", MANIFESTS)
def test_a_dependency_moving_to_the_new_version_counts(release_repo, manifest: str) -> None:
    release_repo.deps[manifest] = _pinned(manifest, "0.4.0")
    release_repo.release("0.4.0")
    release_repo.deps[manifest] = _pinned(manifest, "0.4.1")
    release_repo.release("0.4.1")
    _refused(release_repo.release_check("v0.4.1"), "v0.4.0", manifest)


def test_a_dependency_staying_at_the_previous_version_does_not_count(release_repo) -> None:
    release_repo.deps = {manifest: _pinned(manifest, "0.4.0") for manifest in MANIFESTS}
    release_repo.release("0.4.0")
    release_repo.release("0.4.1")
    _accepted(release_repo.release_check("v0.4.1"))


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


# ---- a release that changes the released formats appends exactly its own version

CONFIG = "shared/config.yaml"


def _release_with_formats(release_repo, previous: str, head: str, version: str = "0.7.0") -> None:
    release_repo.write(CONFIG, previous)
    release_repo.release("0.6.0")
    release_repo.write(CONFIG, head)
    release_repo.release(version)


def test_formats_unchanged_pass(release_repo) -> None:
    release_repo.release("0.6.0")
    release_repo.change(TOOL)
    release_repo.release("0.7.0")
    _accepted(release_repo.release_check("v0.7.0"))


def test_formats_appending_the_own_version_pass(release_repo) -> None:
    _release_with_formats(release_repo, "formats: [0.4.0]\n", "formats: [0.4.0, 0.7.0]\n")
    _accepted(release_repo.release_check("v0.7.0"))


@pytest.mark.parametrize(
    ("previous", "head"),
    [
        ("[0.4.0]", "[0.4.0, 0.8.0]"),
        ("[0.4.0]", "[0.4.0, 0.6.5, 0.7.0]"),
        ("[0.4.0]", "[0.4.1, 0.7.0]"),
        ("[0.4.0, 0.5.0]", "[0.5.0, 0.7.0]"),
        ("[0.4.0, 0.5.0]", "[0.4.0]"),
    ],
    ids=["another-version", "two-versions", "edited-entry", "dropped-entry-and-appended", "dropped-entry"],
)
def test_other_formats_changes_are_refused(release_repo, previous: str, head: str) -> None:
    _release_with_formats(release_repo, f"formats: {previous}\n", f"formats: {head}\n")
    _refused(release_repo.release_check("v0.7.0"), previous, head, "0.7.0")


@pytest.mark.parametrize(
    "previous",
    [
        "format: 0.4.0\n",
        "format: '0.4.0'\n",
        'format: "0.4.0"\n',
        "file: living-architecture.yaml\r\nformat: 0.4.0\r\n",
        "# The repo format.\nfile: living-architecture.yaml\nformat: 0.4.0  # current\n",
    ],
    ids=["plain", "single-quoted", "double-quoted", "crlf", "comments"],
)
def test_a_previous_single_format_reads_as_a_one_entry_list(release_repo, previous: str) -> None:
    _release_with_formats(release_repo, previous, "formats: [0.4.0]\n")
    _accepted(release_repo.release_check("v0.7.0"))


def test_a_previous_single_format_then_the_own_version_appended_passes(release_repo) -> None:
    _release_with_formats(release_repo, "format: 0.4.0\n", "formats: [0.4.0, 0.7.0]\n")
    _accepted(release_repo.release_check("v0.7.0"))


def _release_without_config(release_repo, head: str) -> None:
    (release_repo.root / CONFIG).unlink()
    release_repo.release("0.6.0")
    release_repo.write(CONFIG, head)
    release_repo.release("0.7.0")


def test_a_previous_release_without_the_config_reads_as_no_formats(release_repo) -> None:
    _release_without_config(release_repo, "formats: [0.7.0]\n")
    _accepted(release_repo.release_check("v0.7.0"))


def test_a_previous_release_without_the_config_then_an_older_format_is_refused(release_repo) -> None:
    _release_without_config(release_repo, "formats: [0.4.0]\n")
    _refused(release_repo.release_check("v0.7.0"), "[0.4.0]", "0.7.0")


def test_a_failed_git_read_of_the_previous_formats_fails_naming_the_release(release_repo) -> None:
    _release_with_formats(release_repo, "formats: [0.4.0]\n", "formats: [0.7.0]\n")
    blob = release_repo.git("rev-parse", f"v0.6.0:{CONFIG}").strip()
    (release_repo.root / ".git" / "objects" / blob[:2] / blob[2:]).unlink()
    _refused(release_repo.release_check("v0.7.0"), "cannot read", "v0.6.0")


@pytest.mark.parametrize(
    "previous", ["file: living-architecture.yaml\n", "formats:\n- 0.4.0\n", "format: [0.4.0]\n"],
    ids=["neither", "block-list", "format-list"],
)
def test_unrecognised_previous_formats_fail_naming_the_release(release_repo, previous: str) -> None:
    _release_with_formats(release_repo, previous, "formats: [0.4.0]\n")
    _refused(release_repo.release_check("v0.7.0"), "v0.6.0")
