"""la-typecheck: command splitting, exit combination, which languages apply and the pyright#11919 patch."""

import subprocess
from pathlib import Path

import pytest
import yaml

from living_architecture import cli, lang, typecheck
from living_architecture import config as la_config

VECTORS = next(p for p in Path(__file__).resolve().parents if (p / "shared" / "vectors").is_dir()) / "shared" / "vectors"
SPLITS = yaml.safe_load((VECTORS / "command-split.yaml").read_text(encoding="utf-8"))["cases"]
PATCHED = '{"outcome": "patched", "version": "1.40.2", "count": 1}'
FAKE_CHECKER = """#!/bin/sh
echo "$*" >> checker.log
printf '%s\\n' "$NODE_OPTIONS" > node_options.log
printf '%s\\n' "$LA_PYRIGHT_PATCH_RESULT" > result_path.log
case "$NODE_OPTIONS" in *'--require "'*'/pyright_patch.cjs"') ;; *) echo "fake: NODE_OPTIONS $NODE_OPTIONS" >&2; exit 99 ;; esac
[ "$LA_PYRIGHT_PATCH_VERSIONS" = '["1.40.2"]' ] || { echo "fake: versions $LA_PYRIGHT_PATCH_VERSIONS" >&2; exit 99; }
[ -z '@RESULT@' ] || printf '%s' '@RESULT@' > "$LA_PYRIGHT_PATCH_RESULT"
case "$*" in *--writebaseline*) mkdir -p .basedpyright && echo '{"written": true}' > .basedpyright/baseline.json ;; esac
[ ! -f .basedpyright/baseline.json ] || echo '{"shrunk": true}' > .basedpyright/baseline.json
echo "0 errors, 0 warnings, 0 notes"
exit @CODE@
"""


@pytest.mark.parametrize("vector", SPLITS, ids=lambda v: v["name"])
def test_split_command(vector: dict) -> None:
    if vector.get("error"):
        with pytest.raises(ValueError):
            typecheck.split_command(vector["text"])
    else:
        assert typecheck.split_command(vector["text"]) == vector["words"]


@pytest.mark.parametrize(("codes", "expected"), [([], 0), ([0], 0), ([0, 1], 1), ([1, 0], 1), ([2, 1], 2), ([0, 2], 2)])
def test_combined_exit_is_the_highest(codes: list[int], expected: int) -> None:
    assert typecheck.combined_exit(codes) == expected


def _repo(
    root: Path, files: dict[str, str], *, checker_exit: int = 0, git: bool = True, result: str = PATCHED
) -> Path:
    if git:
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=root, check=True)
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")
    fake = root / ".venv" / "bin" / "basedpyright"
    fake.parent.mkdir(parents=True)
    fake.write_text(FAKE_CHECKER.replace("@RESULT@", result).replace("@CODE@", str(checker_exit)), encoding="utf-8")
    fake.chmod(0o755)
    return root


def _checker_calls(root: Path) -> list[str]:
    log = root / "checker.log"
    return log.read_text(encoding="utf-8").splitlines() if log.exists() else []


@pytest.fixture
def run(monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]):
    def go(root: Path, *argv: str) -> tuple[int, str, str]:
        monkeypatch.chdir(root)
        code = cli.la_typecheck(list(argv))
        out, err = capfd.readouterr()
        return code, out, err

    return go


def test_stray_script_checks_only_python(tmp_path: Path, run) -> None:
    root = _repo(tmp_path, {"pyproject.toml": "", "a.py": "X = 1\n", "docs/static/app.js": "x;\n"})
    code, out, err = run(root)
    assert (code, _checker_calls(root)) == (0, [""])
    assert "checking python with basedpyright" in err
    assert "typescript" not in err + out


def test_explicit_entry_without_markers(tmp_path: Path, run) -> None:
    config = f"format: {la_config.current_format()}\ncommands: {{typecheck: {{python: basedpyright -p python}}}}\n"
    root = _repo(tmp_path, {"living-architecture.yaml": config, "python/a.py": "X = 1\n"})
    assert run(root)[0] == 0
    assert _checker_calls(root) == ["-p python"]


def test_null_turns_a_language_off(tmp_path: Path, run) -> None:
    config = f"format: {la_config.current_format()}\ncommands: {{typecheck: {{python: null}}}}\n"
    root = _repo(tmp_path, {"living-architecture.yaml": config, "pyproject.toml": "", "a.py": "X = 1\n"})
    code, _, err = run(root)
    assert (code, _checker_calls(root)) == (0, [])
    assert "nothing to check" in err


def test_no_applicable_language(tmp_path: Path, run) -> None:
    root = _repo(tmp_path, {"README.md": "x\n", "a.py": "X = 1\n"})
    code, _, err = run(root)
    assert (code, _checker_calls(root)) == (0, [])
    assert "nothing to check" in err


def test_not_a_git_repo(tmp_path: Path, run) -> None:
    root = _repo(tmp_path, {"pyproject.toml": "", "a.py": "X = 1\n"}, git=False)
    code, _, err = run(root)
    assert (code, _checker_calls(root)) == (2, [])
    assert "not inside a git repository" in err


@pytest.mark.parametrize(("checker_exit", "expected"), [(0, 0), (1, 1), (2, 2), (3, 2)])
def test_python_exit_codes(tmp_path: Path, run, checker_exit: int, expected: int) -> None:
    root = _repo(tmp_path, {"pyproject.toml": "", "a.py": "X = 1\n"}, checker_exit=checker_exit)
    assert run(root)[0] == expected


@pytest.mark.parametrize("checker_exit", [0, 1])
def test_write_baseline_appends_the_flag_and_exits_0(tmp_path: Path, run, checker_exit: int) -> None:
    root = _repo(tmp_path, {"pyproject.toml": "", "a.py": "X = 1\n"}, checker_exit=checker_exit)
    assert run(root, "--write-baseline")[0] == 0
    assert _checker_calls(root) == ["--writebaseline"]


def test_write_baseline_skips_an_existing_baseline(tmp_path: Path, run) -> None:
    files = {"pyproject.toml": "", "a.py": "X = 1\n", ".basedpyright/baseline.json": '{"files": {}}\n'}
    root = _repo(tmp_path, files)
    code, _, err = run(root, "--write-baseline")
    assert (code, _checker_calls(root)) == (2, [])
    assert ".basedpyright/baseline.json exists, skipped" in err


def _log(root: Path, name: str) -> str:
    return (root / name).read_text(encoding="utf-8").rstrip("\n")


PYTHON_REPO = {"pyproject.toml": "", "a.py": "X = 1\n"}
NOT_APPLIED = ("la-typecheck: python: basedpyright loaded no basedpyright, so the pyright#11919 patch was not applied;"
               " run basedpyright under Node and keep NODE_OPTIONS")
UNVERIFIED = '{"outcome": "unverified", "version": "1.39.10", "count": 1}'
UNVERIFIED_TEXT = ("la-typecheck: python: the pyright#11919 patch is verified for basedpyright 1.40.2, but 1.39.10 is"
                   " installed; pin a verified version")
MISMATCH = '{"outcome": "mismatch", "version": "1.40.2", "count": 0}'
MISMATCH_TEXT = ("la-typecheck: python: basedpyright 1.40.2 has the pyright#11919 line 0 times, not once;"
                 " reinstall basedpyright")
PATCH_TEXTS = (NOT_APPLIED, UNVERIFIED_TEXT, MISMATCH_TEXT)


def test_preload_alone_without_inherited_node_options(tmp_path: Path, run, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NODE_OPTIONS", raising=False)
    root = _repo(tmp_path, PYTHON_REPO)
    assert run(root)[0] == 0
    assert _log(root, "node_options.log") == f'--require "{lang.PYRIGHT_PATCH_PRELOAD}"'


def test_preload_appended_to_inherited_node_options(tmp_path: Path, run, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NODE_OPTIONS", "--max-old-space-size=4096")
    root = _repo(tmp_path, PYTHON_REPO)
    assert run(root)[0] == 0
    assert _log(root, "node_options.log") == f'--max-old-space-size=4096 --require "{lang.PYRIGHT_PATCH_PRELOAD}"'


def test_result_file_lives_in_a_temp_dir_removed_after_the_run(tmp_path: Path, run) -> None:
    root = _repo(tmp_path, PYTHON_REPO)
    assert run(root)[0] == 0
    result = Path(_log(root, "result_path.log"))
    assert result.is_absolute()
    assert not result.parent.exists()


def test_preload_is_shipped_with_the_package() -> None:
    assert lang.PYRIGHT_PATCH_PRELOAD.name == "pyright_patch.cjs"
    assert lang.PYRIGHT_PATCH_PRELOAD.is_file()


def test_patch_env_sets_the_protocol_variables(tmp_path: Path) -> None:
    result = tmp_path / "patch.json"
    env = lang.pyright_patch_env({"PATH": "/bin"}, result=result, versions=["1.40.2", "1.40.3"])
    assert env == {
        "PATH": "/bin",
        "NODE_OPTIONS": f'--require "{lang.PYRIGHT_PATCH_PRELOAD}"',
        "LA_PYRIGHT_PATCH_RESULT": str(result),
        "LA_PYRIGHT_PATCH_VERSIONS": '["1.40.2", "1.40.3"]',
    }


def test_patch_env_quotes_a_preload_path_with_spaces(tmp_path: Path) -> None:
    preload = tmp_path / "with spaces" / "pyright_patch.cjs"
    env = lang.pyright_patch_env({"NODE_OPTIONS": "--trace-warnings"}, result=tmp_path / "r.json", versions=["1.40.2"],
                                 preload=preload)
    assert env["NODE_OPTIONS"] == f'--trace-warnings --require "{preload}"'


def test_patch_env_leaves_the_given_environment_alone(tmp_path: Path) -> None:
    base = {"NODE_OPTIONS": "--trace-warnings"}
    lang.pyright_patch_env(base, result=tmp_path / "r.json", versions=["1.40.2"])
    assert base == {"NODE_OPTIONS": "--trace-warnings"}


def test_read_pyright_patch_absent(tmp_path: Path) -> None:
    assert lang.read_pyright_patch(tmp_path / "missing.json") is None


@pytest.mark.parametrize(("text", "outcome", "version", "count"), [
    (PATCHED, "patched", "1.40.2", 1),
    (UNVERIFIED, "unverified", "1.39.10", 1),
    ('{"outcome": "mismatch", "version": "1.40.2", "count": 2}', "mismatch", "1.40.2", 2),
])
def test_read_pyright_patch(tmp_path: Path, text: str, outcome: str, version: str, count: int) -> None:
    (tmp_path / "r.json").write_text(text, encoding="utf-8")
    patch = lang.read_pyright_patch(tmp_path / "r.json")
    assert patch is not None
    assert (patch.outcome, patch.version, patch.count) == (outcome, version, count)


@pytest.mark.parametrize("checker_exit", [0, 1, 2])
def test_no_preload_result_is_not_applied(tmp_path: Path, run, checker_exit: int) -> None:
    root = _repo(tmp_path, PYTHON_REPO, checker_exit=checker_exit, result="")
    code, out, err = run(root)
    assert code == 2
    assert out == "0 errors, 0 warnings, 0 notes\n"
    assert err.splitlines()[-1] == NOT_APPLIED


@pytest.mark.parametrize(("result", "text"), [(UNVERIFIED, UNVERIFIED_TEXT), (MISMATCH, MISMATCH_TEXT)])
@pytest.mark.parametrize("checker_exit", [0, 1, 2])
def test_patch_failure_exits_2_after_the_output(tmp_path: Path, run, checker_exit: int, result: str, text: str) -> None:
    root = _repo(tmp_path, PYTHON_REPO, checker_exit=checker_exit, result=result)
    code, out, err = run(root)
    assert code == 2
    assert out == "0 errors, 0 warnings, 0 notes\n"
    assert err.splitlines()[-1] == text


def test_patched_run_prints_no_patch_text(tmp_path: Path, run) -> None:
    root = _repo(tmp_path, PYTHON_REPO, checker_exit=1)
    code, _, err = run(root)
    assert code == 1
    assert [t for t in PATCH_TEXTS if t in err] == []
    assert "pyright#11919" not in err


@pytest.mark.parametrize(("result", "text"), [("", NOT_APPLIED), (UNVERIFIED, UNVERIFIED_TEXT), (MISMATCH, MISMATCH_TEXT)])
@pytest.mark.parametrize("checker_exit", [0, 1])
def test_write_mode_writes_no_baseline_on_a_patch_failure(
    tmp_path: Path, run, checker_exit: int, result: str, text: str
) -> None:
    root = _repo(tmp_path, PYTHON_REPO, checker_exit=checker_exit, result=result)
    code, _, err = run(root, "--write-baseline")
    assert code == 2
    assert not (root / ".basedpyright" / "baseline.json").exists()
    assert "wrote" not in err
    assert err.splitlines()[-1] == text


@pytest.mark.parametrize("result", ["", UNVERIFIED, MISMATCH])
def test_check_mode_restores_the_baseline_on_a_patch_failure(tmp_path: Path, run, result: str) -> None:
    original = '{\n  "files": {"a.py": []}\n}\n'
    root = _repo(tmp_path, {**PYTHON_REPO, ".basedpyright/baseline.json": original}, result=result)
    assert run(root)[0] == 2
    assert (root / ".basedpyright" / "baseline.json").read_text(encoding="utf-8") == original


def test_baseline_removed_by_the_checker_is_restored_on_a_patch_failure(tmp_path: Path, run) -> None:
    root = _repo(tmp_path, {**PYTHON_REPO, ".basedpyright/baseline.json": "{}\n"}, result=UNVERIFIED)
    fake = root / ".venv" / "bin" / "basedpyright"
    fake.write_text(fake.read_text(encoding="utf-8").replace('echo "0 errors', 'rm -r .basedpyright\necho "0 errors'),
                    encoding="utf-8")
    assert run(root)[0] == 2
    assert (root / ".basedpyright" / "baseline.json").read_text(encoding="utf-8") == "{}\n"


def test_read_only_baseline_left_alone_on_a_patch_failure(tmp_path: Path, run) -> None:
    root = _repo(tmp_path, {**PYTHON_REPO, ".basedpyright/baseline.json": "{}\n"}, result=UNVERIFIED)
    baseline = root / ".basedpyright" / "baseline.json"
    baseline.chmod(0o444)
    code, _, err = run(root)
    assert code == 2
    assert err.splitlines()[-1] == UNVERIFIED_TEXT
    assert baseline.read_text(encoding="utf-8") == "{}\n"


def test_patched_check_keeps_the_checkers_baseline_update(tmp_path: Path, run) -> None:
    root = _repo(tmp_path, {**PYTHON_REPO, ".basedpyright/baseline.json": "{}\n"})
    assert run(root)[0] == 0
    assert (root / ".basedpyright" / "baseline.json").read_text(encoding="utf-8") == '{"shrunk": true}\n'


def test_write_mode_writes_the_baseline_when_patched(tmp_path: Path, run) -> None:
    root = _repo(tmp_path, PYTHON_REPO)
    assert run(root, "--write-baseline")[0] == 0
    assert (root / ".basedpyright" / "baseline.json").is_file()


def test_forwarded_python_section_is_patched_too(tmp_path: Path, run) -> None:
    root = _repo(tmp_path, PYTHON_REPO, result="")
    code, _, err = run(root, "--language", "python")
    assert code == 2
    assert err.splitlines()[-1] == NOT_APPLIED
