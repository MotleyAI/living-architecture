"""`dr-refactor` phases: the map loader's every invalid entry, the keep text check, the `checks` refusals no
corpus case can reach (walker gaps, a language server that cannot start or answers an error), and what the
`conflicts` phase is charged with."""

import functools
import re
import sys
from collections.abc import Callable
from pathlib import Path

import pytest
from project_files import file_tree, write_project
from refactor_cli import final_report, run_raw

from living_architecture.contract import message
from living_architecture.lang import language_server
from living_architecture.refactor import timings
from living_architecture.refactor.bindings import BindingCheck
from living_architecture.refactor.map_file import MapError, load_map
from living_architecture.refactor.member_namespace import MemberCheck
from living_architecture.refactor.rename_map import RenameMap, editable_files, keep_checks
from living_architecture.refactor.rename_union import SymbolRename
from living_architecture.refactor.sites import nearest_line, spelled_lines

FAKE_LSP = Path(__file__).with_name("fake_lsp_server.py")
CHECKS = "[resolve]\n[checks]\n"
FOO = "def foo() -> int:\n    return 1\n"
RENAME_FOO = ["rename", "--file", "pkg/a.py", "--symbol", "foo", "--new-name", "bar"]


# ---- the map loader


def test_the_map_loader_names_every_invalid_entry(tmp_path: Path) -> None:
    path = tmp_path / "map.yaml"
    path.write_text(
        "- {file: a.py, symbol: f, new_name: g}\n- {file: a.py, symbol: f}\n"
        "- {file: a.py, symbol: h, new_name: i}\n- {file: a.py, new_name: j}\n",
        encoding="utf-8",
    )
    raw, project = str(path), str(tmp_path)
    with pytest.raises(MapError) as raised:
        load_map(raw, project)
    assert str(raised.value) == "\n".join(
        message("refactor.map-invalid", map=str(path), index=index) for index in (2, 4)
    )


# ---- the keep text check


@pytest.mark.parametrize(
    ("text", "lines"),
    [
        ("a = 1\nb = load()\n", {2}),
        ("x = 1\n", set()),
        ('n = "lo\\x61d"\n', {1}),
        ('x = ("lo"\n     "ad")\n', {1}),
        ("ｌoad = 1\n", {1}),
        ("# load the store\n", {1}),
    ],
    ids=["as-written", "absent", "string-escape", "implicit-concatenation", "nfkc", "comment"],
)
def test_spelled_lines(text: str, lines: set[int]) -> None:
    assert spelled_lines(text, {"load"}) == lines


@pytest.mark.parametrize(
    ("text", "lines"),
    [
        ("# load the store\n", set()),
        ("# the store\n# load reads it\n", set()),
        ("x = 1  # load\n", set()),
        ("y = load()  # load\n", {1}),
        ('s = "# load"\n', {1}),
        ("x = None  # type: load\n", {1}),
        ("x = None  #type:load\n", {1}),
        ("x = None  # a type: load\n", set()),
    ],
    ids=["comment", "multi-line-comment", "trailing-comment", "code-and-comment", "hash-in-string", "type-comment",
         "type-comment-unspaced", "not-a-type-comment"],
)
def test_spelled_lines_without_comments(text: str, lines: set[int]) -> None:
    assert spelled_lines(text, {"load"}, comments=False) == lines


def test_the_keep_text_check_skips_whole_path_keeps(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = write_project(tmp_path / "p", {"pkg/a.py": FOO, "docs/x.py": "y = 1\n"})
    monkeypatch.chdir(root)
    editable = editable_files(root, False)
    refused = keep_checks(["docs", "pkg/a.py", "docs/x.py:1"], root, editable,
                          lambda rel: (root / rel).read_text(encoding="utf-8"), {"load"}, [], set(), docs=False)
    assert [f.lines for f in refused] == [(message("refactor.keep-unmatched", site="docs/x.py:1"),)]


@pytest.mark.parametrize(
    ("edited", "line", "nearest"),
    [([4, 30], 9, 4), ([2, 12], 9, 12), ([12, 6], 9, 6), ([], 9, None), ([9], 9, 9)],
    ids=["before", "after", "tie-takes-the-earlier", "none", "same-line"],
)
def test_nearest_line(edited: list[int], line: int, nearest: int | None) -> None:
    assert nearest_line(edited, line) == nearest


# ---- keeps the check passes or skips


def test_a_keep_on_a_line_holding_only_the_retarget_target_passes_the_checks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = write_project(tmp_path / "p", {
        "pkg/api.py": "def modern() -> int:\n    return 1\n\n\nlegacy = modern\n",
        "pkg/use.py": "from pkg.api import legacy, modern\n\nx = modern()\ny = legacy()\n",
    })
    argv = ["retarget", "--file", "pkg/api.py", "--symbol", "legacy", "--target", "modern", "--keep", "pkg/use.py:3"]
    code, out, err = run_raw(root, argv, monkeypatch, capsys)
    assert (code, out) == (2, "")
    assert "[references 1/1] entry 1: legacy -> modern" in err.splitlines()
    assert "[conflicts]" not in err.splitlines()
    unmatched = message("refactor.keep-unmatched", site="pkg/use.py:3").split(",")[0]
    assert err.splitlines()[-1].startswith(unmatched)


def test_the_keep_text_check_is_skipped_when_an_unresolved_entry_spells_no_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = write_project(tmp_path / "p", {
        "pkg/a.py": FOO,
        "README.md": "# Nothing here\n",
        "map.yaml": "- {file: pkg/a.py, symbol: foo, new_name: bar}\n- {file: pkg/a.py, line: 99, new_name: baz}\n",
    })
    code, out, err = run_raw(root, ["rename-map", "map.yaml", "--keep", "README.md"], monkeypatch, capsys)
    assert (code, out) == (1, "")
    assert err == CHECKS + message("refactor.line-out-of-range", line=99, count=2) + "\n"


def test_a_keep_on_the_renamed_module_file_passes_the_checks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = write_project(tmp_path / "p", {"pkg/a.py": "X = 1\n", "pkg/use.py": "from . import a\n\nprint(a.X)\n"})
    argv = ["--apply", "rename", "--file", "pkg/use.py", "--line", "1", "--col", "15", "--new-name", "b",
            "--keep", "pkg/a.py"]
    code, _out, err = run_raw(root, argv, monkeypatch, capsys)
    assert (code, err) == (0, CHECKS + "[references]\n[conflicts]\n[write]\n")
    assert (root / "pkg" / "a.py").exists()


def test_a_module_rename_onto_a_taken_name_reports_no_unchecked_keep(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = write_project(tmp_path / "p", {"pkg/a.py": "X = 1\n", "pkg/b.py": "Y = 2\n",
                                          "pkg/use.py": "from . import a\n\nprint(a.X)\n"})
    argv = ["rename", "--file", "pkg/use.py", "--line", "1", "--col", "15", "--new-name", "b", "--keep", "pkg/use.py"]
    code, out, err = run_raw(root, argv, monkeypatch, capsys)
    conflict = message("refactor.name-conflict", name="b", path="pkg/b.py", line=1)
    assert (code, out, err) == (1, "", CHECKS + "[references]\n" + conflict + "\n")


# ---- refusals in checks


def test_walker_gaps_in_every_entry_module_refuse_in_the_checks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    restore_rope_visitor: Callable[[str], None],
    annotation_gap: str,
) -> None:
    restore_rope_visitor("_arg")
    shifted = annotation_gap.replace("\n\n", "\n" * 7, 1)
    entries = "".join(f"- {{file: pkg/{name}.py, symbol: foo, new_name: bar}}\n" for name in ("g1", "g2"))
    root = write_project(tmp_path / "p", {"pkg/a.py": FOO, "pkg/g2.py": annotation_gap, "pkg/g1.py": shifted,
                                          "map.yaml": entries})
    before = file_tree(root)
    code, out, err = run_raw(root, ["--apply", "rename-map", "map.yaml"], monkeypatch, capsys)
    gaps = [message("refactor.rope-walk", path=f"pkg/{name}.py", line=line) for name, line in (("g1", 8), ("g2", 3))]
    assert (code, out, err) == (1, "", CHECKS + "".join(f"{gap}\n" for gap in gaps))
    assert file_tree(root) == before


@pytest.mark.parametrize("taken", ["", "\n\ndef bar() -> int:\n    return 3\n"], ids=["free", "new-name-taken"])
def test_a_gap_rope_meets_in_the_rules_refuses_only_its_entry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    restore_rope_visitor: Callable[[str], None],
    annotation_gap: str,
    taken: str,
) -> None:
    # The checker cannot resolve scripts/'s import, so rope walks scripts/use.py only in the rules, after the entry's
    # edit in pkg/a.py; the refused entry's edits then check no name.
    restore_rope_visitor("_arg")
    entries = "- {file: pkg/a.py, symbol: foo, new_name: bar}\n- {file: pkg/a.py, symbol: baz, new_name: qux}\n"
    root = write_project(tmp_path / "p", {
        "pyrightconfig.json": '{"executionEnvironments": [{"root": "scripts"}]}\n',
        "pkg/a.py": FOO + "\n\ndef baz() -> int:\n    return 2\n" + taken,
        "scripts/use.py": annotation_gap,
        "map.yaml": entries,
    })
    before = file_tree(root)
    code, out, err = run_raw(root, ["--apply", "rename-map", "map.yaml"], monkeypatch, capsys)
    entry = {"phase": "rules", "count": 2}
    refused = message("refactor.progress-refused", **entry, n=1, entries=message("refactor.progress-entry", index=1),
                      old="foo", new="bar", refusals=1)
    clean = message("refactor.progress-clean", **entry, n=2, entries=message("refactor.progress-entry", index=2),
                    old="baz", new="qux")
    gap = message("refactor.rope-walk", path="scripts/use.py", line=3)
    assert (code, out) == (1, "")
    assert err.splitlines()[-5:] == [refused, gap, clean, CONFLICTS, gap]
    assert file_tree(root) == before


def test_a_language_server_that_cannot_start_refuses_with_its_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    missing = str(tmp_path / "no-such-node")
    monkeypatch.setattr(language_server, "_bundled_command", lambda: [missing, "--stdio"])
    root = write_project(tmp_path / "p", {"pkg/a.py": FOO})
    before = file_tree(root)
    code, out, err = run_raw(root, ["--apply", *RENAME_FOO], monkeypatch, capsys)
    error = f"{missing}: no such file or directory"
    cause = message("refactor.checker-not-started", error=error)
    assert (code, out, err) == (1, "", CHECKS + message("refactor.pyright-failed") + "\n" + cause + "\n")
    assert file_tree(root) == before


def test_a_language_server_that_cannot_start_is_reported_when_no_entry_resolves(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    missing = str(tmp_path / "no-such-node")
    monkeypatch.setattr(language_server, "_bundled_command", lambda: [missing, "--stdio"])
    root = write_project(tmp_path / "p", {"pkg/a.py": FOO})
    code, out, err = run_raw(root, ["rename", "--file", "pkg/a.py", "--line", "99", "--new-name", "bar"], monkeypatch,
                             capsys)
    error = f"{missing}: no such file or directory"
    expected = [message("refactor.line-out-of-range", line=99, count=2), message("refactor.pyright-failed"),
                message("refactor.checker-not-started", error=error)]
    assert (code, out, err) == (1, "", CHECKS + "".join(f"{line}\n" for line in expected))


def test_a_language_server_answering_an_error_refuses_with_its_answer_and_stderr(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    record = tmp_path / "record.jsonl"
    command = [sys.executable, str(FAKE_LSP), "error-on-initialize", str(record)]
    monkeypatch.setattr(language_server, "_bundled_command", lambda: command)
    root = write_project(tmp_path / "p", {"pkg/a.py": FOO})
    code, out, err = run_raw(root, RENAME_FOO, monkeypatch, capsys)
    expected = [message("refactor.pyright-failed"), message("refactor.checker-error", error="fake failure"),
                "  fake: initialize failed"]
    assert (code, out, err) == (1, "", CHECKS + "".join(f"{line}\n" for line in expected))


# ---- the conflicts phase

SECOND = 1_000_000_000
CONFLICTS = message("refactor.progress-phase", phase="conflicts")
_TIMING = re.compile(
    re.escape(message("refactor.timing", phase="PHASE", seconds="0.00"))
    .replace("PHASE", r"(\S+)")
    .replace(re.escape("0.00"), r"(\d+\.\d\d)")
)
KEYED_MODELS = "from pydantic import BaseModel\n\n\nclass Model(BaseModel):\n    columns: list[int] = []\n"
STORE = (
    "class Store:\n    def load(self) -> int:\n        return 1\n\n    def fetch(self) -> int:\n        return 2\n\n\n"
    "def run(s: Store) -> int:\n    return s.load()\n"
)
HIER = (
    "class Base:\n    def ping(self) -> int:\n        return 1\n\n\n"
    "class Sub(Base):\n    def ping(self) -> int:\n        return 2\n"
)
MODULE_CAPTURE = {"pkg/a.py": "X = 1\n", "pkg/use.py": "from pkg import a\n\nb = 2\n\nprint(a.X, b)\n"}
FAIL_FAST = {
    "pkg/store.py": "class Store:\n    def drop(self) -> int:\n        return 1\n\n    def load(self) -> int:\n"
                    "        return 2\n",
    "pkg/loose.py": "def loose(s):\n    return s.drop()\n",
    "map.yaml": "- {file: pkg/store.py, symbol: Store.drop, new_name: discard}\n"
                "- {file: pkg/store.py, symbol: Store.load, new_name: fetch}\n",
}


class Clock:
    def __init__(self) -> None:
        self.now = 0

    def __call__(self) -> int:
        return self.now


def _slowed(monkeypatch: pytest.MonkeyPatch, owner: type, name: str) -> None:
    """Every `--timings` run reads a fake clock that only `owner.name` advances, by 100 s a call."""
    clock = Clock()
    monkeypatch.setattr(timings, "Timer", functools.partial(timings.Timer, clock))
    original = getattr(owner, name)

    @functools.wraps(original)
    def slow(*args: object, **kwargs: object) -> object:
        clock.now += 100 * SECOND
        return original(*args, **kwargs)

    monkeypatch.setattr(owner, name, slow)


def _times(err: str) -> dict[str, str]:
    return {m[1]: m[2] for line in err.splitlines() if (m := _TIMING.fullmatch(line))}


def _charged_to_conflicts_only(err: str) -> None:
    times = _times(err)
    assert times.get("conflicts", "0.00") != "0.00", times
    assert {p: s for p, s in times.items() if p not in ("conflicts", "total") and s != "0.00"} == {}


@pytest.mark.parametrize(
    ("files", "argv", "owner", "method"),
    [
        pytest.param(
            {"pkg/models.py": KEYED_MODELS, "pkg/use.py": "from pkg.models import Model\n\nb = Model(columns=[], fields=[])\n"},
            ["rename", "--file", "pkg/models.py", "--symbol", "Model.columns", "--new-name", "fields"],
            SymbolRename, "check_conflicts", id="keyed",
        ),
        pytest.param(
            {"pkg/store.py": STORE},
            ["rename", "--file", "pkg/store.py", "--symbol", "Store.load", "--new-name", "fetch"],
            MemberCheck, "conflicts", id="member",
        ),
        pytest.param(
            {"pkg/a.py": FOO + "\n\ndef bar() -> int:\n    return 2\n\n\nx = foo()\n"},
            RENAME_FOO,
            BindingCheck, "conflicts", id="binding",
        ),
        pytest.param(
            {"pkg/hier.py": HIER, "map.yaml": "- {file: pkg/hier.py, symbol: Base.ping, new_name: a}\n"
                                              "- {file: pkg/hier.py, symbol: Sub.ping, new_name: b}\n"},
            ["rename-map", "map.yaml"],
            RenameMap, "merged", id="map",
        ),
    ],
)
def test_a_conflict_check_is_charged_to_the_conflicts_phase_announced_before_its_finding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
    files: dict[str, str], argv: list[str], owner: type, method: str,
) -> None:
    _slowed(monkeypatch, owner, method)
    root = write_project(tmp_path / "p", files)
    code, out, err = run_raw(root, ["--timings", *argv], monkeypatch, capsys)
    assert (code, out) == (1, "")
    lines = err.splitlines()
    finding = final_report(err).splitlines()[0]
    assert CONFLICTS in lines
    assert lines.index(CONFLICTS) < lines.index(finding)
    _charged_to_conflicts_only(err)


def test_a_module_rename_checks_its_bindings_in_the_conflicts_phase(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _slowed(monkeypatch, BindingCheck, "conflicts")
    root = write_project(tmp_path / "p", MODULE_CAPTURE)
    argv = ["--timings", "rename", "--file", "pkg/use.py", "--line", "1", "--col", "17", "--new-name", "b"]
    code, out, err = run_raw(root, argv, monkeypatch, capsys)
    conflict = message("refactor.name-conflict", name="b", path="pkg/use.py", line=3)
    assert (code, out) == (1, "")
    assert err.startswith(CHECKS + "[references]\n" + CONFLICTS + "\n" + conflict + "\n")
    _charged_to_conflicts_only(err)


@pytest.mark.parametrize(("flags", "announced"), [([], True), (["--fail-fast"], False)], ids=["every-group", "fail-fast"])
def test_a_fail_fast_stop_skips_the_conflicts_phase(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
    flags: list[str], announced: bool,
) -> None:
    root = write_project(tmp_path / "p", FAIL_FAST)
    code, out, err = run_raw(root, ["rename-map", "map.yaml", *flags], monkeypatch, capsys)
    assert (code, out) == (1, "")
    assert (CONFLICTS in err.splitlines()) is announced
