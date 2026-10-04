import json
import subprocess
import sys
from pathlib import Path

import pytest

from living_architecture import cli, conventions
from living_architecture.config import CONFIG_FILENAME


def _violations(tmp_path: Path, source: str, rel: str = "pkg/mod.py") -> list[str]:
    path = tmp_path / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source)
    violations, _ = conventions.check_file(path, rel=rel)
    return [f"{v.line}:{v.rule}" for v in violations]


def test_import_after_code(tmp_path):
    assert _violations(tmp_path, "import os\nX = 1\nimport sys\n") == ["3:import-not-top"]


def test_import_inside_function(tmp_path):
    assert _violations(tmp_path, "def f():\n    import os\n") == ["2:import-not-top"]


def test_import_wrappers_are_prologue(tmp_path):
    src = '"""Doc."""\nfrom typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    import os\ntry:\n    import x\nexcept ImportError:\n    x = None\nY = 1\n'
    assert _violations(tmp_path, src) == []


def test_waiver(tmp_path):
    src = "def f():\n    import os  # ALLOW(import-not-top): breaks a cycle\n"
    assert _violations(tmp_path, src) == []


def test_waiver_needs_reason(tmp_path):
    src = "def f():\n    import os  # ALLOW(import-not-top):\n"
    assert _violations(tmp_path, src) == ["2:import-not-top"]


def test_test_only_rules(tmp_path):
    src = "import pytest\n\ndef test_x():\n    assert a and b\n    with pytest.raises(E):\n        f(g())\n"
    assert _violations(tmp_path, src, rel="tests/test_x.py") == ["4:composite-assert", "5:raises-single-throw"]
    assert _violations(tmp_path, src, rel="pkg/x.py") == []


@pytest.mark.parametrize(
    ("rel", "expected"),
    [("tests/a.py", True), ("pkg/test_a.py", True), ("pkg/a_test.py", True), ("conftest.py", True),
     ("pkg/a.py", False)],
)
def test_is_test_file(rel, expected):
    assert conventions.is_test_file(rel) is expected


def test_syntax_error_reported(tmp_path):
    assert _violations(tmp_path, "def (:\n") == ["1:syntax-error"]


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "config", "user.email", "t@example.com")
    _git(tmp_path, "config", "user.name", "t")
    (tmp_path / "old.py").write_text("def f():\n    import os\n")
    _git(tmp_path, "add", "old.py")
    _git(tmp_path, "commit", "-q", "-m", "base")
    _git(tmp_path, "update-ref", "refs/remotes/origin/main", "HEAD")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_base_diff_checks_only_changed_files(repo, capsys):
    (repo / "committed.py").write_text("X = 1\n")
    _git(repo, "add", "committed.py")
    _git(repo, "commit", "-q", "-m", "change")
    (repo / "old.py").write_text("def f():\n    import os\n\n\ndef g():\n    import sys\n")
    assert cli.la_check_conventions(["--base", "main"]) == 1
    out = capsys.readouterr().out
    assert "old.py:2: [import-not-top]" in out
    assert "old.py:6: [import-not-top]" in out
    assert "gate: RED" in out


def test_clean_diff(repo, capsys):
    (repo / "new.py").write_text("import os\n\nX = os.sep\n")
    _git(repo, "add", "new.py")
    _git(repo, "commit", "-q", "-m", "change")
    assert cli.la_check_conventions(["--base", "main"]) == 0
    assert "gate: CLEAR" in capsys.readouterr().out


def test_unknown_base(repo, capsys):
    assert cli.la_check_conventions(["--base", "nope"]) == 2
    assert "la-check-conventions:" in capsys.readouterr().err


def test_text_ratio_uses_config_cap_and_exempt(repo, capsys):
    (repo / "wordy.py").write_text("# a\n# b\nX = 1\n")
    (repo / "surface.py").write_text("# a\n# b\n# c\nY = 1\n")
    assert cli.la_check_conventions(["--file", "wordy.py"]) == 1
    assert "[text-ratio] source" in capsys.readouterr().out
    (repo / CONFIG_FILENAME).write_text("conventions: {text_ratio_max: 0.7, exempt: [surface.py]}\n")
    assert cli.la_check_conventions(["--file", "wordy.py", "--file", "surface.py"]) == 0
    assert "exempt, skipped: surface.py" in capsys.readouterr().err


def test_cli_cap_overrides_config(repo):
    (repo / "wordy.py").write_text("# a\nX = 1\n")
    assert cli.la_check_conventions(["--file", "wordy.py", "--text-ratio-cap", "60"]) == 0
    assert cli.la_check_conventions(["--file", "wordy.py", "--text-ratio-cap", "40"]) == 1


def test_ratio_groups_tests_separately(repo, capsys):
    (repo / "tests").mkdir()
    (repo / "tests" / "test_a.py").write_text("# a\n# b\n# c\nX = 1\n")
    (repo / "a.py").write_text("X = 1\n")
    assert cli.la_check_conventions(["--file", "tests/test_a.py", "--file", "a.py"]) == 1
    out = capsys.readouterr().out
    assert "[text-ratio] tests" in out
    assert "[text-ratio] source" not in out


def test_pr_resolves_base_via_gh(repo, fake_gh, monkeypatch):
    fake_gh.route((["pr", "view", "7", "baseRefName"], {"baseRefName": "main"}))
    monkeypatch.setenv("PATH", fake_gh.env()["PATH"])
    monkeypatch.setenv("FAKE_GH_ROUTES", str(fake_gh.routes_file))
    monkeypatch.setenv("FAKE_GH_LOG", str(fake_gh.log_file))
    assert cli.la_check_conventions(["7", "--repo", "o/r"]) == 0
    assert fake_gh.calls()[0]["argv"][:3] == ["pr", "view", "7"]


def test_requires_a_target():
    with pytest.raises(SystemExit) as exc:
        cli.la_check_conventions([])
    assert exc.value.code == 2


# ---- routing, labels and waivers on carried line text


@pytest.mark.parametrize(
    ("path", "language"),
    [("src/a.py", "python"), ("web/b.ts", "typescript"), ("web/b.tsx", "typescript"), ("x.mts", "typescript"),
     ("x.cts", "typescript"), ("x.js", "typescript"), ("x.jsx", "typescript"), ("x.mjs", "typescript"),
     ("x.cjs", "typescript"), ("types/x.d.ts", "typescript"), ("README.md", None), ("a.pyc", None),
     ("a.PY", None), ("Makefile", None), ("src/données.py", "python")],
)
def test_language_of(path, language):
    assert conventions.language_of(path) == language


@pytest.mark.parametrize(
    ("languages", "label"),
    [([], "source"), (["python"], ".py"), (["typescript"], "TS/JS"), (["python", "typescript"], ".py and TS/JS"),
     (["typescript", "python"], ".py and TS/JS")],
)
def test_files_label(languages, label):
    assert conventions.files_label(languages) == label


@pytest.mark.parametrize(
    ("text", "rule", "language", "waived"),
    [
        ("import a  # ALLOW(import-not-top): cycle", "import-not-top", "python", True),
        ("import a  #ALLOW(import-not-top):x", "import-not-top", "python", True),
        ("import { a } from 'a'; // ALLOW(import-not-top): generated", "import-not-top", "typescript", True),
        ("import { a } from 'a'; # ALLOW(import-not-top): generated", "import-not-top", "typescript", False),
        ("import a  // ALLOW(import-not-top): cycle", "import-not-top", "python", False),
        ("import a  # ALLOW(composite-assert): wrong rule", "import-not-top", "python", False),
        ("import a  # ALLOW(import-not-top):", "import-not-top", "python", False),
        ("import a  # allow(import-not-top): lowercase", "import-not-top", "python", False),
        ("x = 1  # ALLOW(text-ratio): never", "text-ratio", "python", False),
    ],
)
def test_waived_on_carried_text(text, rule, language, waived):
    assert conventions.waived(text=text, rule=rule, language=language) is waived


def test_facts_keep_the_order_of_a_path_list_longer_than_a_command_line(tmp_path):
    _git(tmp_path, "init", "-q", "-b", "main")
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "real.py").write_text("X = 1\nimport os\n")
    paths = [f"pkg/{'d' * 60}/{i:05d}_{'m' * 40}.py" for i in range(30_000, 0, -1)]
    paths.insert(15_000, "pkg/real.py")
    stdin = json.dumps(paths)
    assert len(stdin) > 2 * 1024 * 1024
    proc = subprocess.run(
        [str(Path(sys.executable).parent / "la-check-conventions"), "--language", "python", "--emit", "facts"],
        cwd=tmp_path, input=stdin, capture_output=True, text=True, check=False,
    )
    assert proc.returncode == 0, proc.stderr
    files = json.loads(proc.stdout)["files"]
    assert [f["path"] for f in files] == paths
    assert {f["status"] for f in files[:15_000]} == {"missing"}
    assert files[15_000]["status"] == "ok"
    assert [d["line"] for d in files[15_000]["detections"]] == [2]
