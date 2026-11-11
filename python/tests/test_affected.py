"""`la-affected-tests`: changed tests plus the tests whose imports reach a changed file, through the PyPI twin."""

import io
import json
import os
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

from living_architecture import __version__, cli
from living_architecture.contract import contract_hash, language, schema, validate

TYPESCRIPT_IDENTITY = f"typescript {__version__} {contract_hash()}"
BASE = {
    "src/pkg/__init__.py": "",
    "src/pkg/a.py": "from pkg import b\n",
    "src/pkg/b.py": "X = 1\n",
    "tests/test_a.py": "import pkg.a\n",
    "tests/test_c.py": "import os\n",
}


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def _write(repo: Path, files: dict[str, str]) -> None:
    for rel, text in files.items():
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text(text, encoding="utf-8")


def _commit(repo: Path, message: str = "work") -> None:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", message)


def _init(path: Path, files: dict[str, str]) -> Path:
    _git(path, "init", "-q", "-b", "main")
    _git(path, "config", "user.email", "t@example.com")
    _git(path, "config", "user.name", "t")
    _write(path, files)
    _commit(path, "base")
    _git(path, "update-ref", "refs/remotes/origin/main", "HEAD")
    _git(path, "checkout", "-q", "-b", "feat")
    return path


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    monkeypatch.chdir(root)
    return _init(root, BASE)


@pytest.fixture
def restrict_path(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> Callable[..., None]:
    """Call after setup: PATH holds only `extra` dirs and `git`, so no other twin or runner is reachable."""
    bin_dir = tmp_path_factory.mktemp("git-only")
    git = shutil.which("git")
    assert git is not None
    (bin_dir / "git").symlink_to(git)

    def restrict(*extra: Path) -> None:
        monkeypatch.setenv("PATH", os.pathsep.join([*map(str, extra), str(bin_dir)]))

    return restrict


def _affected(capsys: pytest.CaptureFixture[str], *args: str) -> tuple[int, list[str], str]:
    code = cli.la_affected_tests(list(args))
    captured = capsys.readouterr()
    return code, captured.out.splitlines(), captured.err


def test_nothing_changed(repo, capsys):
    assert _affected(capsys, "--base", "main") == (0, [], "")


def test_missing_base_is_a_usage_error():
    with pytest.raises(SystemExit) as exc:
        cli.la_affected_tests([])
    assert exc.value.code == 2


def test_changed_test_only(repo, capsys):
    _write(repo, {"tests/test_c.py": "import sys\n"})
    _commit(repo)
    assert _affected(capsys, "--base", "main") == (0, ["tests/test_c.py"], "")


def test_transitive_reach_leaves_unrelated_tests_out(repo, capsys):
    _write(repo, {"src/pkg/b.py": "X = 2\n"})
    _commit(repo)
    assert _affected(capsys, "--base", "main") == (0, ["tests/test_a.py"], "")


def test_changed_test_helper_selects_its_importers(repo, capsys):
    _write(repo, {"tests/helpers.py": "Y = 1\n", "tests/test_x.py": "import helpers\n"})
    _commit(repo, "helpers")
    _git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    _write(repo, {"tests/helpers.py": "Y = 2\n"})
    assert _affected(capsys, "--base", "main") == (0, ["tests/helpers.py", "tests/test_x.py"], "")


def test_type_only_edge_counts(repo, capsys):
    _write(repo, {"tests/test_t.py": "from typing import TYPE_CHECKING\n\nif TYPE_CHECKING:\n    from pkg import b\n"})
    _commit(repo, "typed")
    _git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    _write(repo, {"src/pkg/b.py": "X = 2\n"})
    assert _affected(capsys, "--base", "main") == (0, ["tests/test_a.py", "tests/test_t.py"], "")


def test_deleted_module_still_imported(repo, capsys):
    _git(repo, "rm", "-q", "src/pkg/b.py")
    _commit(repo)
    assert _affected(capsys, "--base", "main") == (0, ["tests/test_a.py"], "")


def test_deleted_test_is_not_printed(repo, capsys):
    _git(repo, "rm", "-q", "tests/test_c.py")
    _commit(repo)
    assert _affected(capsys, "--base", "main") == (0, [], "")


def test_rename_selects_importers_of_the_old_name(repo, capsys):
    _git(repo, "mv", "src/pkg/b.py", "src/pkg/b2.py")
    _commit(repo)
    assert _affected(capsys, "--base", "main") == (0, ["tests/test_a.py"], "")


def test_untracked_test_listed_and_ignored_one_not(repo, capsys):
    _write(repo, {"tests/test_new.py": "", "tests/test_ignored.py": "", ".gitignore": "tests/test_ignored.py\n"})
    assert _affected(capsys, "--base", "main") == (0, ["tests/test_new.py"], "")


def test_staged_only_and_unstaged_only(repo, capsys):
    _write(repo, {"tests/test_a.py": "import pkg.a\nimport os\n", "tests/test_c.py": "import sys\n"})
    _git(repo, "add", "tests/test_a.py")
    assert _affected(capsys, "--base", "main") == (0, ["tests/test_a.py", "tests/test_c.py"], "")


def test_output_does_not_depend_on_the_working_directory(repo, capsys, monkeypatch):
    _write(repo, {"src/pkg/b.py": "X = 2\n"})
    from_root = _affected(capsys, "--base", "main")
    monkeypatch.chdir(repo / "src" / "pkg")
    assert _affected(capsys, "--base", "main") == from_root


def test_import_cycle_terminates(repo, capsys):
    _write(repo, {"src/pkg/b.py": "from pkg import a\n"})
    _commit(repo, "cycle")
    _git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    _write(repo, {"src/pkg/b.py": "from pkg import a\nX = 3\n"})
    assert _affected(capsys, "--base", "main") == (0, ["tests/test_a.py"], "")


def test_architecture_index_changes_nothing(repo, capsys):
    _write(repo, {"src/pkg/b.py": "X = 2\n"})
    without = _affected(capsys, "--base", "main")
    _write(repo, {"architecture/index.yaml": "python:\n  root_package: pkg\n  source_root: src\n"})
    _commit(repo)
    assert _affected(capsys, "--base", "main") == without


def test_code_point_order_and_unusual_names(repo, capsys):
    names = ["tests/test_é.py", "tests/test_my file.py", "tests/test_a.py", "tests/test_B.py"]
    _git(repo, "config", "core.quotePath", "true")
    _write(repo, dict.fromkeys(names, "import os\n"))
    assert _affected(capsys, "--base", "main") == (
        0, ["tests/test_B.py", "tests/test_a.py", "tests/test_my file.py", "tests/test_é.py"], ""
    )


def test_yaml_only_change(repo, capsys, restrict_path):
    restrict_path()
    _write(repo, {"config.yaml": "a: 1\n"})
    assert _affected(capsys, "--base", "main") == (0, [], "")


def test_unparseable_test_keeps_its_lexical_imports(repo, capsys):
    _write(repo, {"tests/test_broken.py": "from pkg import (\n    b,\n)\n\ndef broken(:\n"})
    _commit(repo, "broken")
    _git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    _write(repo, {"src/pkg/b.py": "X = 2\n"})
    assert _affected(capsys, "--base", "main") == (0, ["tests/test_a.py", "tests/test_broken.py"], "")


# ---- setup and git failures: exit 2, nothing on stdout


def test_missing_base_ref(repo, capsys):
    code, out, err = _affected(capsys, "--base", "nope")
    assert (code, out, err) == (2, [], "la-affected-tests: git rev-parse --verify --quiet origin/nope failed\n")


def test_git_missing_from_path(repo, capsys, monkeypatch, tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.setenv("PATH", str(empty))
    assert _affected(capsys, "--base", "main") == (2, [], "la-affected-tests: git rev-parse --verify --quiet origin/main failed\n")


@pytest.mark.skipif(not hasattr(os, "geteuid") or os.geteuid() == 0, reason="needs a non-root POSIX user")
def test_an_unreadable_importer_fails(repo, capsys):
    _write(repo, {"src/pkg/b.py": "X = 2\n"})
    (repo / "src/pkg/a.py").chmod(0)
    code, out, err = _affected(capsys, "--base", "main")
    assert (code, out, err.startswith("la-affected-tests: "), "a.py" in err) == (2, [], True, True)


def test_not_a_git_repository(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    code, out, err = _affected(capsys, "--base", "main")
    assert (code, out, err.startswith("la-affected-tests: ")) == (2, [], True)


def test_unborn_head(repo, capsys):
    _git(repo, "checkout", "-q", "--orphan", "fresh")
    code, out, err = _affected(capsys, "--base", "main")
    assert (code, out, err.startswith("la-affected-tests: ")) == (2, [], True)


def test_changed_path_with_a_newline(repo, capsys):
    _write(repo, {"tests/test_new\nline.py": ""})
    code, out, err = _affected(capsys, "--base", "main")
    assert (code, out, err.startswith("la-affected-tests: "), "test_new" in err) == (2, [], True, True)


def test_graph_path_with_a_newline(repo, capsys):
    _write(repo, {"src/odd\nname.py": ""})
    _commit(repo, "odd")
    _git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    _write(repo, {"src/pkg/b.py": "X = 2\n"})
    code, out, err = _affected(capsys, "--base", "main")
    assert (code, out, "odd" in err) == (2, [], True)


def test_changed_path_not_utf8(repo, capsys):
    Path(os.fsdecode(bytes(repo) + b"/tests/test_\xff.py")).write_bytes(b"")
    code, out, err = _affected(capsys, "--base", "main")
    assert (code, out, err.startswith("la-affected-tests: ")) == (2, [], True)


# ---- the other language


def test_own_language_change_needs_no_twin(repo, capsys, restrict_path):
    restrict_path()
    _write(repo, {"src/pkg/b.py": "X = 2\n"})
    assert _affected(capsys, "--base", "main") == (0, ["tests/test_a.py"], "")


def test_other_twin_unreachable(repo, capsys, restrict_path):
    restrict_path()
    _write(repo, {"web/b.ts": "export const b = 1;\n"})
    code, out, err = _affected(capsys, "--base", "main")
    expected_err = (
        f"la-affected-tests: the typescript twin (living-architecture {__version__}) is not reachable; install it"
        f" with: npm install -g living-architecture@{__version__}\n"
    )
    assert (code, out, err) == (2, [], expected_err)


def test_data_change_in_a_repo_with_typescript_needs_the_npm_twin(repo, capsys, restrict_path):
    _write(repo, {"web/a.test.ts": "import data from './data.json';\n", "web/data.json": "{}\n"})
    _commit(repo, "web")
    _git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    restrict_path()
    _write(repo, {"web/data.json": "{\"a\": 1}\n"})
    code, out, err = _affected(capsys, "--base", "main")
    assert (code, out, "typescript twin" in err) == (2, [], True)


def _stub_twin(directory: Path, response: str) -> Path:
    """An npm twin whose `la-affected-tests` records its argv, stdin and LA_FORWARDED, then prints `response`."""
    directory.mkdir()
    cat = shutil.which("cat")
    assert cat is not None
    doctor = directory / "la-doctor"
    doctor.write_text(f"#!/bin/sh\necho '{TYPESCRIPT_IDENTITY}'\n")
    affected = directory / "la-affected-tests"
    affected.write_text(
        "#!/bin/sh\n"
        f'echo "$* $LA_FORWARDED" > "{directory}/argv"\n'
        f'{cat} > "{directory}/stdin"\n'
        f"{cat} <<'EOF'\n{response}\nEOF\n"
    )
    for path in (doctor, affected):
        path.chmod(0o755)
    return directory


def _response(tests: list[str], **overrides: str) -> str:
    document = {"language": "typescript", "version": __version__, "contract_hash": contract_hash(), "tests": tests}
    return json.dumps({**document, **overrides})


def test_two_languages_are_unioned(repo, capsys, restrict_path, tmp_path):
    stub = _stub_twin(tmp_path / "npm", _response(["web/b.test.ts", "web/a.test.ts"]))
    _write(repo, {"src/pkg/b.py": "X = 2\n", "web/b.ts": "export const b = 1;\n"})
    _git(repo, "rm", "-q", "tests/test_c.py")
    restrict_path(stub)
    assert _affected(capsys, "--base", "main") == (0, ["tests/test_a.py", "web/a.test.ts", "web/b.test.ts"], "")
    assert (stub / "argv").read_text() == "--language typescript 1\n"
    request = json.loads((stub / "stdin").read_text())
    assert validate(schema("affected-request"), request) == []
    assert request == {"changes": [
        {"path": "src/pkg/b.py", "deleted": False},
        {"path": "tests/test_c.py", "deleted": True},
        {"path": "web/b.ts", "deleted": False},
    ]}


@pytest.mark.parametrize(
    "response",
    [_response(["web/a.test.ts"], version="0.0.0"), _response(["web/a.test.ts"], language="python"),
     _response(["web/a.test.ts"], contract_hash="0" * 64), "not json", json.dumps({"tests": ["web/a.test.ts"]}),
     _response(["/abs/a.test.ts"])],
    ids=["wrong-version", "wrong-language", "wrong-contract-hash", "not-json", "schema-invalid", "absolute-path"],
)
def test_invalid_twin_response(repo, capsys, restrict_path, tmp_path, response):
    stub = _stub_twin(tmp_path / "npm", response)
    _write(repo, {"src/pkg/b.py": "X = 2\n", "web/b.ts": "export const b = 1;\n"})
    restrict_path(stub)
    code, out, err = _affected(capsys, "--base", "main")
    assert (code, out, err.startswith("la-affected-tests: ")) == (2, [], True)


# ---- the internal language request


def _request(monkeypatch: pytest.MonkeyPatch, document: object) -> None:
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(json.dumps(document).encode("utf-8"))))


def test_internal_request_returns_the_python_selection(repo, capsys, monkeypatch):
    _git(repo, "rm", "-q", "src/pkg/b.py")
    _request(monkeypatch, {"changes": [{"path": "src/pkg/b.py", "deleted": True}]})
    assert cli.la_affected_tests(["--language", "python"]) == 0
    document = json.loads(capsys.readouterr().out)
    assert validate(schema("affected-response"), document) == []
    assert document == {"language": "python", "version": __version__, "contract_hash": contract_hash(),
                        "tests": ["tests/test_a.py"]}


def test_internal_request_for_the_other_language_is_refused(repo, capsys, monkeypatch):
    _request(monkeypatch, {"changes": []})
    assert cli.la_affected_tests(["--language", "typescript"]) == 2
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize("path", ["/abs/a.py", "../a.py", "a/../b.py", "./a.py", "a\\b.py", ""])
def test_internal_request_rejects_unsafe_paths(repo, capsys, monkeypatch, path):
    _request(monkeypatch, {"changes": [{"path": path, "deleted": False}]})
    assert cli.la_affected_tests(["--language", "python"]) == 2
    assert capsys.readouterr().out == ""


def test_internal_request_not_json(repo, capsys, monkeypatch):
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(b"[nope")))
    assert cli.la_affected_tests(["--language", "python"]) == 2
    assert capsys.readouterr().out == ""


# ---- shared contract pieces


@pytest.mark.parametrize(
    ("document", "valid"),
    [({"changes": [{"path": "src/a.py", "deleted": False}]}, True), ({"changes": []}, True),
     ({"changes": [{"path": "src/a.py"}]}, False), ({"changes": [{"path": "a//b.py", "deleted": False}]}, False),
     ({}, False)],
)
def test_request_schema(document, valid):
    assert (validate(schema("affected-request"), document) == []) is valid


def test_response_schema_requires_identity():
    good = {"language": "typescript", "version": "1.2.3", "contract_hash": "ab", "tests": ["web/a.test.ts"]}
    assert validate(schema("affected-response"), good) == []
    assert validate(schema("affected-response"), {k: v for k, v in good.items() if k != "contract_hash"}) != []


def test_imports_non_source_facts():
    assert (language("python")["imports_non_source"], language("typescript")["imports_non_source"]) == (False, True)
