"""la's conformance cases, and the checks on the corpus and the runner."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

import conformance_runner
from conformance_runner import (
    CASES,
    CORPUS,
    NEUTRAL,
    OVERLAY_DIRS,
    REPO_ROOT,
    UPDATE,
    Variant,
    case_args,
    case_files,
    check_case,
    check_json,
    load_case,
    materialize,
    package_cases,
    package_of,
    run_case,
    selected,
    selected_runs,
    substitute,
    variants,
)


@pytest.mark.parametrize(
    ("case_dir", "variant"), [pytest.param(c, v, id=i) for c, v, i in selected_runs(package_cases("la"))]
)
def test_case(case_dir: Path, variant: Variant, tmp_path: Path) -> None:
    problems = check_case(case_dir, tmp_path, update=UPDATE, variant=variant)
    assert not problems, "\n".join(problems)


def test_corpus_is_not_empty() -> None:
    assert len(CASES) > 100


@pytest.mark.parametrize("case_dir", CASES, ids=lambda p: p.name)
def test_case_declares_kind_and_exit(case_dir: Path) -> None:
    case = load_case(case_dir)
    assert case["kind"] in ("neutral", "paired", "adapter")
    assert case["kind"] == "neutral" or case["languages"]
    assert isinstance(case["expect"]["exit"], int)


def test_no_corpus_file_is_git_ignored() -> None:
    """An ignored fixture passes locally but is never committed, so the case breaks in CI."""
    out = subprocess.run(
        ["git", "ls-files", "--others", "--ignored", "--exclude-standard", "--", "conformance"],
        cwd=REPO_ROOT, capture_output=True, text=True, check=True,
    ).stdout
    assert out.splitlines() == []



def _ignored(rel: str) -> bool:
    return subprocess.run(["git", "check-ignore", "-q", "--no-index", "--", rel], cwd=REPO_ROOT, check=False).returncode == 0


def test_only_the_root_local_config_is_git_ignored() -> None:
    assert _ignored("living-architecture.local.yaml")
    assert not _ignored("conformance/la/cases/config-local-empty/repo/living-architecture.local.yaml")


def _wrong_golden_case(tmp_path: Path) -> Path:
    case_dir = tmp_path / "la" / "cases" / "wrong"
    case_dir.mkdir(parents=True)
    (case_dir / "case.yaml").write_text(
        "kind: neutral\ncommand: la-config\nargs: [get, issue_key_pattern]\nexpect: {exit: 0}\n", encoding="utf-8"
    )
    (case_dir / "stdout").write_text("not the real output\n", encoding="utf-8")
    (case_dir / "stderr").write_text("", encoding="utf-8")
    return case_dir


def test_wrong_golden_fails_with_a_diff_and_stays_untouched(tmp_path: Path) -> None:
    case_dir = _wrong_golden_case(tmp_path)
    problems = check_case(case_dir, tmp_path / "run")
    assert "-not the real output" in "\n".join(problems)
    assert (case_dir / "stdout").read_text(encoding="utf-8") == "not the real output\n"


def test_update_mode_rewrites_the_golden(tmp_path: Path) -> None:
    case_dir = _wrong_golden_case(tmp_path)
    assert check_case(case_dir, tmp_path / "run", update=True) == []
    assert (case_dir / "stdout").read_text(encoding="utf-8") == "[A-Z][A-Z0-9]+-\\d+\n"


def test_git_status_is_compared_with_its_golden(tmp_path: Path) -> None:
    case_dir = _wrong_golden_case(tmp_path)
    (case_dir / "case.yaml").write_text(
        "kind: neutral\ncommand: la-config\nargs: [get, issue_key_pattern]\n"
        "git: [{write: {a.txt: x}}]\nexpect: {exit: 0, stdout: ignore, git_status: true}\n",
        encoding="utf-8",
    )
    (case_dir / "git-status").write_text("?? b.txt\n", encoding="utf-8")
    assert "+?? a.txt" in "\n".join(check_case(case_dir, tmp_path / "run"))
    (case_dir / "git-status").write_text("?? a.txt\n", encoding="utf-8")
    assert check_case(case_dir, tmp_path / "run2") == []


def test_update_mode_refuses_an_unexpected_exit(tmp_path: Path) -> None:
    case_dir = _wrong_golden_case(tmp_path)
    (case_dir / "case.yaml").write_text(
        "kind: neutral\ncommand: la-config\nargs: [get, nope]\nexpect: {exit: 0}\n", encoding="utf-8"
    )
    assert check_case(case_dir, tmp_path / "run", update=True)
    assert (case_dir / "stdout").read_text(encoding="utf-8") == "not the real output\n"


# ---- case model


def _case(**fields: object) -> dict:
    return {"kind": "neutral", "command": "la-arch-check", "expect": {"exit": 0}, **fields}


def test_paired_case_runs_once_per_language_with_its_own_overlay() -> None:
    runs = variants(_case(kind="paired", languages=["python", "typescript"]))
    assert [(v.fixture_languages, v.golden) for v in runs] == [(["python"], "python"), (["typescript"], "typescript")]


def test_neutral_case_applies_every_listed_overlay() -> None:
    [variant] = variants(_case(languages=["python", "typescript"]))
    assert (variant.fixture_languages, variant.golden) == (["python", "typescript"], None)


def test_paired_case_args_may_be_keyed_by_language() -> None:
    case = _case(kind="paired", languages=["python", "typescript"], args={"python": ["a.py"], "typescript": ["a.ts", 1]})
    assert [case_args(case, v) for v in variants(case)] == [["a.py"], ["a.ts", "1"]]


def test_paired_case_files_may_be_keyed_by_language() -> None:
    case = _case(kind="paired", languages=["python", "typescript"], expect={"exit": 0, "files": {"python": ["a.py"], "typescript": ["a.ts"]}})
    assert [case_files(case, v) for v in variants(case)] == [["a.py"], ["a.ts"]]


def test_case_files_default_to_one_list_for_every_variant() -> None:
    case = _case(kind="paired", languages=["python", "typescript"], expect={"exit": 0, "files": ["shared.txt"]})
    assert [case_files(case, v) for v in variants(case)] == [["shared.txt"], ["shared.txt"]]


def test_native_selection_needs_own_fixture_languages() -> None:
    case = _case(languages=["python", "typescript"])
    [variant] = variants(case)
    assert not selected(case, variant, "python", cross=False)
    assert selected(case, variant, "python", cross=True)


def test_language_free_case_is_native_to_both_twins() -> None:
    case = _case(command="la-config")
    assert selected(case, NEUTRAL, "python", cross=False)
    assert selected(case, NEUTRAL, "typescript", cross=False)


@pytest.mark.parametrize("command", ["trmv-refactor", "trmv-compliance", "trmv-mock-lint"])
def test_trmv_commands_are_native_to_both_twins(command: str) -> None:
    case = _case(command=command, kind="adapter", languages=["typescript"])
    [variant] = variants(case)
    assert selected(case, variant, "typescript", cross=False)
    assert not selected(case, variant, "python", cross=False)


@pytest.mark.parametrize("command", ["la-check-conventions", "la-count-comments", "la-typecheck"])
def test_conventions_and_typecheck_are_neutral(command: str) -> None:
    case = _case(command=command, kind="adapter", languages=["typescript"])
    [variant] = variants(case)
    assert selected(case, variant, "typescript", cross=False)
    assert not selected(case, variant, "python", cross=False)


def test_pinned_case_runs_only_through_its_twin() -> None:
    case = _case(twin="typescript", command="la-check-conventions")
    assert selected(case, NEUTRAL, "typescript", cross=False)
    assert not selected(case, NEUTRAL, "python", cross=True)


def test_pinned_case_forwarding_to_the_other_twin_runs_only_with_its_bins() -> None:
    case = _case(twin="python", command="trmv-refactor", kind="adapter", languages=["typescript"])
    [variant] = variants(case)
    assert not selected(case, variant, "python", cross=False, bins={"python"})
    assert selected(case, variant, "python", cross=False, bins={"python", "typescript"})


def test_pinned_case_without_the_other_twin_needs_no_bins() -> None:
    case = _case(twin="python", command="trmv-refactor", kind="adapter", languages=["typescript"], other_twin="absent")
    [variant] = variants(case)
    assert selected(case, variant, "python", cross=False, bins={"python"})


def test_later_overlay_overwrites_an_earlier_one(tmp_path: Path) -> None:
    case_dir = tmp_path / "la" / "cases" / "both"
    for sub, text in (("python", "py\n"), ("node", "ts\n")):
        (case_dir / sub).mkdir(parents=True)
        (case_dir / sub / "shared.txt").write_text(text, encoding="utf-8")
    case = _case(languages=["python", "typescript"], git="none")
    [variant] = variants(case)
    repo, _ = materialize(case_dir, case, tmp_path / "run", variant)
    assert (repo / "shared.txt").read_text(encoding="utf-8") == "ts\n"


def test_format_placeholder_fills_committed_configs_and_write_steps_only(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(conformance_runner, "current_format", lambda: "7.8.9")
    case_dir = tmp_path / "la" / "cases" / "fmt"
    texts = {
        "living-architecture.yaml": "format: <FORMAT>\r\ntracker: linear\r\n",
        "sub/living-architecture.yaml": "format: <FORMAT>\n",
        "other/living-architecture.yaml": "format: <FORMAT>\n",
        "living-architecture.local.yaml": "format: <FORMAT>\n",
        "notes.md": "<FORMAT>\n",
    }
    for rel, text in texts.items():
        (case_dir / "repo" / rel).parent.mkdir(parents=True, exist_ok=True)
        (case_dir / "repo" / rel).write_bytes(text.encode("utf-8"))
    case = _case(git=[{"write": {"written.txt": "<FORMAT> <VERSION>\n"}}], args=["--root", "sub", "<FORMAT>"])
    repo, _ = materialize(case_dir, case, tmp_path / "run", NEUTRAL)
    assert (repo / "living-architecture.yaml").read_bytes() == b"format: 7.8.9\r\ntracker: linear\r\n"
    assert (repo / "sub" / "living-architecture.yaml").read_text(encoding="utf-8") == "format: 7.8.9\n"
    assert (repo / "other" / "living-architecture.yaml").read_text(encoding="utf-8") == "format: <FORMAT>\n"
    assert (repo / "living-architecture.local.yaml").read_text(encoding="utf-8") == "format: <FORMAT>\n"
    assert (repo / "notes.md").read_text(encoding="utf-8") == "<FORMAT>\n"
    assert (repo / "written.txt").read_text(encoding="utf-8") == f"7.8.9 {conformance_runner.__version__}\n"
    assert substitute("<FORMAT>", tmp_path) == "<FORMAT>"


def test_series_placeholders_fill_args_env_fake_executables_and_write_steps(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(conformance_runner, "__version__", "012.34.5-rc1")
    case = _case(
        env={"SERIES": "<MAJOR>|<MINOR>"},
        bins=[{"dir": "fake", "files": {"exe": "<MAJOR>.<MINOR>.x\n"}}],
        git=[{"write": {"written.txt": "<MAJOR> <MINOR> <VERSION>\n"}}],
    )
    root = tmp_path / "run"
    repo, env = materialize(tmp_path / "la" / "cases" / "series", case, root, NEUTRAL)
    assert substitute("--plugin=<MAJOR>.<MINOR>.0", root) == "--plugin=012.34.0"
    assert env["SERIES"] == "012|34"
    assert (root / "bins" / "fake" / "exe").read_text(encoding="utf-8") == "012.34.x\n"
    assert (repo / "written.txt").read_text(encoding="utf-8") == "012 34 012.34.5-rc1\n"


def test_format_is_read_only_when_a_placeholder_needs_it(tmp_path: Path, monkeypatch) -> None:
    def unavailable() -> str:
        raise AssertionError("current format read without a placeholder")

    monkeypatch.setattr(conformance_runner, "current_format", unavailable)
    case_dir = tmp_path / "la" / "cases" / "plain"
    (case_dir / "repo").mkdir(parents=True)
    (case_dir / "repo" / "living-architecture.yaml").write_bytes(b"\xff tracker: linear\n")
    repo, _ = materialize(case_dir, _case(git=[{"write": {"a.txt": "a\n"}}]), tmp_path / "run", NEUTRAL)
    assert (repo / "living-architecture.yaml").read_bytes() == b"\xff tracker: linear\n"


def test_orphan_step_leaves_head_unborn_with_the_index_kept(tmp_path: Path) -> None:
    case_dir = tmp_path / "la" / "cases" / "orphan"
    case_dir.mkdir(parents=True)
    steps = [{"write": {"a.txt": "a\n"}}, {"commit": "init"}, {"orphan": "fresh"}]
    repo, env = materialize(case_dir, _case(git=steps), tmp_path / "run", NEUTRAL)
    head = subprocess.run(["git", "rev-parse", "--verify", "-q", "HEAD"], cwd=repo, env=env, capture_output=True, check=False)
    staged = subprocess.run(["git", "ls-files"], cwd=repo, env=env, capture_output=True, text=True, check=True).stdout
    assert (head.returncode, staged) == (1, "a.txt\n")


@pytest.mark.parametrize("case_dir", CASES, ids=lambda p: p.name)
def test_case_overlays_belong_to_listed_languages(case_dir: Path) -> None:
    case = load_case(case_dir)
    listed = {OVERLAY_DIRS[language] for language in case.get("languages", [])}
    present = {sub for sub in OVERLAY_DIRS.values() if (case_dir / sub).is_dir()}
    assert present <= listed
    assert case.get("twin") in (None, "python", "typescript")


def test_json_stream_ignores_formatting_but_not_array_order(tmp_path: Path) -> None:
    golden = tmp_path / "stdout"
    golden.write_text('{"a": [1, 2], "b": null, "v": "<VERSION>"}\n', encoding="utf-8")
    assert check_json(golden, json.dumps({"b": None, "a": [1, 2], "v": conformance_runner.__version__})) == []
    assert check_json(golden, '{"a": [2, 1], "b": null}')
    assert check_json(golden, '{"a": [1, 2]} trailing')


def test_every_case_runs_with_a_fresh_cache_directory_of_its_own(tmp_path: Path) -> None:
    case_dir = CORPUS / "trmv" / "cases" / "refactor-rename-dry-run"
    case = load_case(case_dir)
    dirs = []
    for root in (tmp_path / "one", tmp_path / "two"):
        repo, env = materialize(case_dir, case, root, variants(case)[0])
        cache = Path(env["LA_CACHE_DIR"])
        assert cache.is_dir()
        assert not any(cache.iterdir())
        assert cache.is_relative_to(root)
        assert not cache.is_relative_to(repo)
        dirs.append(cache)
    assert dirs[0] != dirs[1]


@pytest.mark.parametrize(("tree", "command"), [("la", "trmv-config"), ("trmv", "la-config")])
def test_a_case_invoking_the_other_packages_command_is_refused(tree: str, command: str, tmp_path: Path) -> None:
    case_dir = tmp_path / tree / "cases" / "foreign"
    case_dir.mkdir(parents=True)
    (case_dir / "case.yaml").write_text(f"kind: neutral\ncommand: {command}\nexpect: {{exit: 0}}\n", encoding="utf-8")
    assert package_of(case_dir) == tree
    with pytest.raises(ValueError, match=f"{command} is not a {tree} command"):
        run_case(case_dir, tmp_path / "run")
