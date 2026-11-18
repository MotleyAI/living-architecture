"""`dr-refactor rename-map` holds each phase's state only until its last reader, with its output unchanged."""

from __future__ import annotations

import gc
import subprocess
import weakref
from collections import Counter, defaultdict
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

import pytest
import yaml
from project_files import write_project
from refactor_cli import final_report, run, run_raw, template_regex

from living_architecture.contract import message
from living_architecture.lang import (
    ExportRequest,
    FactQuery,
    LanguageServer,
    OccurrenceIndex,
    language_server,
)
from living_architecture.refactor import rename_map
from living_architecture.refactor.entry_location import EntryLocator
from living_architecture.refactor.index_cache import IndexCache
from living_architecture.refactor.keyed import TypeFacts
from living_architecture.refactor.literal_rename import LiteralRename
from living_architecture.refactor.module_rename import ModuleRename
from living_architecture.refactor.occurrence_index import RunIndex, ServerSession
from living_architecture.refactor.outcomes import Finding
from living_architecture.refactor.progress import Progress
from living_architecture.refactor.python_source import SourceFile
from living_architecture.refactor.rename_map import RenameMap
from living_architecture.refactor.rename_union import RenameOptions, Session, SymbolRename
from living_architecture.refactor.retarget import ImportNeed
from living_architecture.refactor.retarget_imports import plan_imports
from living_architecture.refactor.text_edits import TextEdit
from living_architecture.refactor.text_tables import TextTables

Refs = defaultdict[str, list[weakref.ReferenceType[object]]]


def _lines(*lines: str) -> str:
    return "\n".join(lines)


def _map(entries: Sequence[Mapping[str, object]]) -> str:
    return yaml.safe_dump(entries, sort_keys=False, allow_unicode=True)


def _project(tmp_path: Path, files: dict[str, str], entries: Sequence[Mapping[str, object]]) -> Path:
    """A git repo (prose files come from git) holding `files` and the map."""
    root = write_project(tmp_path / "proj", {**files, "map.yaml": _map(entries)})
    _ = subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    return root.resolve()


def _alive(refs: Refs) -> dict[str, int]:
    _ = gc.collect()
    return {label: sum(r() is not None for r in found) for label, found in refs.items()}


class Lifetimes:
    """Weak references to the tracked objects made before `rules` ends (or the report starts), and how many of each
    label are alive when the report starts."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.monkeypatch: pytest.MonkeyPatch = monkeypatch
        self.refs: Refs = defaultdict(list)
        self.recording: bool = True
        self.at_report: dict[str, int] | None = None
        rules, report = RenameMap.rules, RenameMap.report

        def ending_rules(engine: RenameMap, *args: object, **kwargs: object) -> object:
            try:
                return rules(engine, *args, **kwargs)  # pyright: ignore[reportArgumentType]
            finally:
                self.recording = False

        def checked_report(engine: RenameMap, *args: object, **kwargs: object) -> object:
            self.recording = False
            self.at_report = _alive(self.refs)
            return report(engine, *args, **kwargs)  # pyright: ignore[reportArgumentType]

        monkeypatch.setattr(RenameMap, "rules", ending_rules)
        monkeypatch.setattr(RenameMap, "report", checked_report)

    def track(self, cls: type, label: Callable[[object], str | None]) -> None:
        init = cls.__init__

        def tracking(obj: object, *args: object, **kwargs: object) -> None:
            init(obj, *args, **kwargs)
            name = label(obj) if self.recording else None
            if name is not None:
                self.refs[name].append(weakref.ref(obj))

        self.monkeypatch.setattr(cls, "__init__", tracking)

    def workers(self) -> None:
        for cls in (SymbolRename, LiteralRename, ModuleRename):
            self.track(cls, lambda _: "worker")

    def rules_state(self, root: Path) -> None:
        """Every worker, the run's index, type facts, entry locator and text tables, and each parsed file."""
        self.workers()
        for cls, label in ((RunIndex, "index"), (TypeFacts, "type facts"), (EntryLocator, "locator"),
                           (TextTables, "tables")):
            self.track(cls, lambda _, label=label: label)

        def source(obj: object) -> str:
            assert isinstance(obj, SourceFile)
            return "snapshot" if obj.path.is_relative_to(root) else "outside"

        self.track(SourceFile, source)


ENGINE = """\
class Engine:
    def save_model(self, m: int) -> None:
        print(m)

    def save(self, m: int) -> None:
        return self.save_model(m)
"""
ENGINE_USE = "from pkg.engine import Engine\n\n\ndef use(engine: Engine) -> None:\n    engine.save(1)\n"
KEYED_MODELS = "from pydantic import BaseModel\n\n\nclass Model(BaseModel):\n    columns: list[int] = []\n"
KEYED_USE = 'from pkg.models import Model\n\n\ndef use() -> Model:\n    return Model.model_validate({"columns": []})\n'


def test_no_rules_state_outlives_rules(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _project(tmp_path, {
        "pkg/engine.py": ENGINE, "pkg/use.py": ENGINE_USE, "pkg/models.py": KEYED_MODELS, "pkg/keyed.py": KEYED_USE,
        "README.md": "Call `Model.columns` and `Engine.save` here.\n",
    }, [
        {"file": "pkg/models.py", "symbol": "Model.columns", "new_name": "fields"},
        {"file": "pkg/engine.py", "symbol": "Engine.save", "retarget": "Engine.save_model"},
    ])
    lifetimes = Lifetimes(monkeypatch)
    lifetimes.rules_state(root)
    code, _out, err = run(root, ["rename-map", "map.yaml", "--docs"], monkeypatch, capsys)
    compound = message("refactor.compound", path="pkg/engine.py", line=2, name="save_model", old="save")
    assert (code, err) == (0, f"{compound}\n")
    labels = ("worker", "index", "type facts", "locator", "tables", "snapshot", "outside")
    assert lifetimes.at_report == dict.fromkeys(labels, 0)


SHARED_OLD = """\
class A:
    def save(self) -> int:
        return 1

    def load(self) -> int:
        return 3


class B:
    def save(self) -> int:
        return 2


def use(a: A, b: B) -> int:
    return a.save() + b.save() + a.load()
"""


def test_a_finished_groups_workers_die_before_the_next_groups_rules(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _project(tmp_path, {"pkg/m.py": SHARED_OLD}, [
        {"file": "pkg/m.py", "symbol": "A.save", "new_name": "store"},
        {"file": "pkg/m.py", "symbol": "B.save", "new_name": "keep"},
        {"file": "pkg/m.py", "symbol": "A.load", "new_name": "fetch"},
    ])
    refs: Refs = defaultdict(list)
    init, rules = SymbolRename.__init__, SymbolRename.rules
    seen: list[dict[str, int]] = []

    def tracking(self: SymbolRename, *args: object, **kwargs: object) -> None:
        init(self, *args, **kwargs)  # pyright: ignore[reportArgumentType]
        refs[self.old].append(weakref.ref(self))

    def checked_rules(self: SymbolRename, *args: object) -> None:
        if self.old == "load" and not seen:
            seen.append(_alive(refs))
        rules(self, *args)  # pyright: ignore[reportArgumentType]

    monkeypatch.setattr(SymbolRename, "__init__", tracking)
    monkeypatch.setattr(SymbolRename, "rules", checked_rules)
    code, _out, err = run(root, ["rename-map", "map.yaml"], monkeypatch, capsys)
    assert (code, err) == (0, "")
    assert seen == [{"save": 0, "load": 1}]


KEYWORD = "class A:\n    def old(self) -> int:\n        return 1\n\n    def other(self) -> int:\n        return 2\n"
KEYWORD_MAP = [
    {"file": "pkg/a.py", "symbol": "A.old", "new_name": "class"},
    {"file": "pkg/a.py", "symbol": "A.other", "new_name": "more"},
]
LOOSE = {
    "pkg/store.py": "class Store:\n    def drop(self) -> int:\n        return 1\n\n    def load(self) -> int:\n        return 2\n",
    "pkg/loose.py": "def loose(s):\n    return s.drop()\n",
}
LOOSE_MAP = [
    {"file": "pkg/store.py", "symbol": "Store.drop", "new_name": "discard"},
    {"file": "pkg/store.py", "symbol": "Store.load", "new_name": "fetch"},
]
UNCHANGED = KEYWORD + "\n\ndef use(a: A) -> int:\n    return a.old() + a.other()\n"
UNCHANGED_OUT = _lines(
    "Renaming <old> to <old>:",
    "Renaming <other> to <more>:",
    "",
    "",
    "--- a/pkg/a.py",
    "+++ b/pkg/a.py",
    "@@ -2,9 +2,9 @@",
    "     def old(self) -> int:",
    "         return 1",
    " ",
    "-    def other(self) -> int:",
    "+    def more(self) -> int:",
    "         return 2",
    " ",
    " ",
    " def use(a: A) -> int:",
    "-    return a.old() + a.other()",
    "+    return a.old() + a.more()",
    "",
    "",
    "",
    "DRY-RUN. 1 file(s) would change. Re-run with --apply.",
    "",
)
LOOSE_BLIND = [
    message("compliance.attr-blindspot", path="pkg/loose.py", line=2, receiver="s", attr="drop", type="Unknown"),
    message("refactor.blindspots", count=1, names=".drop"),
]


@pytest.mark.parametrize(("files", "entries", "flags", "expected"), [
    pytest.param({"pkg/a.py": KEYWORD}, KEYWORD_MAP, ["--fail-fast"], (1, "", [message("refactor.cannot-rename")]),
                 id="fail-fast-in-references"),
    pytest.param(LOOSE, LOOSE_MAP, ["--fail-fast"], (1, "", LOOSE_BLIND), id="fail-fast-in-rules"),
    pytest.param({"pkg/a.py": KEYWORD}, KEYWORD_MAP, [], (1, "", [message("refactor.cannot-rename")]),
                 id="failed-entry"),
    pytest.param({"pkg/a.py": UNCHANGED}, [{"file": "pkg/a.py", "symbol": "A.old", "new_name": "old"},
                                            {"file": "pkg/a.py", "symbol": "A.other", "new_name": "more"}],
                 [], (0, UNCHANGED_OUT, []), id="new-name-equals-old"),
])
def test_every_path_ends_rules_the_same_way(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], files: dict[str, str],
    entries: list[dict[str, object]], flags: list[str], expected: tuple[int, str, list[str]],
) -> None:
    root = _project(tmp_path, files, entries)
    lifetimes = Lifetimes(monkeypatch)
    lifetimes.workers()
    code, out, err = run(root, ["rename-map", "map.yaml", *flags], monkeypatch, capsys)
    actual = (code, out, err.splitlines())
    assert actual == expected
    assert lifetimes.at_report == {"worker": 0}


SHARED_MENTIONED = """\
class A:
    def save(self) -> int:
        return 1


class B:
    def save(self) -> int:
        return 2


def use(a: A, b: B) -> int:
    # save both
    print("save")
    return a.save() + b.save()
"""
LEFTOVER = template_regex(message("refactor.leftover", path="PATH", line=999, where="WHERE", old="OLD"),
                          path="PATH", line="999", where="WHERE", old="OLD")


def test_each_leftover_is_held_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _project(tmp_path, {
        "pkg/m.py": SHARED_MENTIONED,
        "README.md": "# Notes\n\nCall `save` to persist. A.save and B.save differ.\n\nsave everything.\n",
    }, [
        {"file": "pkg/m.py", "symbol": "A.save", "new_name": "store"},
        {"file": "pkg/m.py", "symbol": "B.save", "new_name": "keep"},
    ])
    held: list[Counter[tuple[str, int, int, str]]] = []
    report = RenameMap.report

    def counted_report(engine: RenameMap, *args: object) -> object:
        _ = gc.collect()
        objects: list[object] = gc.get_objects()
        held.append(Counter((o.path, o.line, o.col, o.text) for o in objects
                            if isinstance(o, Finding) and LEFTOVER.fullmatch(o.text)))
        return report(engine, *args)  # pyright: ignore[reportArgumentType]

    monkeypatch.setattr(RenameMap, "report", counted_report)
    code, _out, err = run(root, ["rename-map", "map.yaml", "--docs"], monkeypatch, capsys)
    assert code == 0
    assert err.splitlines() == [
        message("refactor.leftover", path="README.md", line=3, where="prose", old="save"),
        message("refactor.leftover", path="README.md", line=5, where="prose", old="save"),
        message("refactor.leftover", path="pkg/m.py", line=12, where="comment", old="save"),
        message("refactor.leftover", path="pkg/m.py", line=13, where="string", old="save"),
    ]
    assert len(held) == 1
    assert max(held[0].values(), default=0) <= 1, held[0]


@pytest.mark.parametrize(("keep", "expected"), [
    pytest.param("README.md", (0, [
        message("refactor.keep-unneeded", site="README.md"),
        message("refactor.leftover", path="NOTES.md", line=1, where="prose", old="save"),
        message("refactor.leftover", path="pkg/m.py", line=12, where="comment", old="save"),
        message("refactor.leftover", path="pkg/m.py", line=13, where="string", old="save"),
    ]), id="whole-file"),
    pytest.param("README.md:3", (2, [message("refactor.keep-unmatched", site="README.md:3")]), id="line"),
])
def test_a_kept_leftover_is_dropped_without_matching_its_keep(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], keep: str,
    expected: tuple[int, list[str]],
) -> None:
    root = _project(tmp_path, {"pkg/m.py": SHARED_MENTIONED, "README.md": "# Notes\n\nsave everything.\n",
                               "NOTES.md": "save it\n"}, [
        {"file": "pkg/m.py", "symbol": "A.save", "new_name": "store"},
        {"file": "pkg/m.py", "symbol": "B.save", "new_name": "keep"},
    ])
    code, _out, err = run(root, ["rename-map", "map.yaml", "--docs", "--keep", keep], monkeypatch, capsys)
    actual = (code, err.splitlines())
    assert actual == expected


def _leftover(end: int | None) -> Finding:
    return Finding(path="pkg/a.py", line=1, col=10, end=end, text="pkg/a.py:1: leftover")


def _edit(start: int, end: int) -> TextEdit:
    return TextEdit(path="pkg/a.py", start=start, end=end, new_text="x")


@pytest.mark.parametrize(("ends", "edits", "printed"), [
    ([12, 20], [], True),
    ([12, 20], [_edit(15, 16)], True),
    ([12, 20], [_edit(10, 11)], False),
    ([12, 20], [_edit(11, 12), _edit(19, 20)], False),
    ([None, 20], [_edit(15, 16)], True),
    ([None, 20], [_edit(10, 11)], False),
], ids=["uncovered", "one-span-covered", "both-covered", "both-covered-apart", "col-span-uncovered", "col-covered"])
def test_a_leftover_is_printed_iff_one_of_its_spans_is_uncovered(
    tmp_path: Path, ends: list[int | None], edits: list[TextEdit], printed: bool
) -> None:
    root = write_project(tmp_path / "proj", {"pkg/a.py": "x = 1\n"})
    engine = RenameMap(root, [], RenameOptions(), "map.yaml", Progress())
    store = rename_map.Leftovers()  # pyright: ignore[reportAttributeAccessIssue]
    for end in ends:
        store.add(_leftover(end))
    engine.leftovers = store  # pyright: ignore[reportAttributeAccessIssue]
    assert [f.text for f in engine.findings([], edits, [])] == (["pkg/a.py:1: leftover"] if printed else [])


CORE = "class Model:\n    pass\n\n\nclass Part:\n    pass\n"
COMPAT = "from pkg.core import Model, Part\n\nCONST = 1\nAcmeModel = Model\nAcmePart = Part\n"
IMPORTS = {
    "pkg/core.py": CORE,
    "pkg/compat.py": COMPAT,
    "pkg/use.py": "from pkg.compat import CONST, AcmePart, AcmeModel\nfrom pkg.core import Model\nfrom pkg.core import Part\n\n"
                  "x = CONST, AcmeModel(), AcmePart(), Model, Part\n",
    "pkg/held.py": "from pkg.compat import AcmeModel, AcmePart\n\ny = AcmePart()\nz = AcmeModel()\n",
}
RETARGETS = [{"file": "pkg/compat.py", "symbol": alias, "retarget": target}
             for alias, target in (("AcmeModel", "Model"), ("AcmePart", "Part"))]
TARGET_RENAMES = [{"file": "pkg/core.py", "symbol": old, "new_name": new} for old, new in (("Model", "Item"), ("Part", "Piece"))]
IMPORTS_OUT = _lines(
    "Retargeting <AcmeModel> to <Model>:",
    "Retargeting <AcmePart> to <Part>:",
    "",
    "",
    "--- a/pkg/held.py",
    "+++ b/pkg/held.py",
    "@@ -1,4 +1,5 @@",
    "-from pkg.compat import AcmeModel, AcmePart",
    "+from pkg.compat import AcmePart",
    "+from pkg.core import Model",
    " ",
    " y = AcmePart()",
    "-z = AcmeModel()",
    "+z = Model()",
    "",
    "--- a/pkg/use.py",
    "+++ b/pkg/use.py",
    "@@ -1,5 +1,4 @@",
    "-from pkg.compat import CONST, AcmePart, AcmeModel",
    "-from pkg.core import Model",
    "-from pkg.core import Part",
    "+from pkg.compat import CONST",
    "+from pkg.core import Part, Model",
    " ",
    "-x = CONST, AcmeModel(), AcmePart(), Model, Part",
    "+x = CONST, Model(), Part(), Model, Part",
    "",
    "",
    "",
    "DRY-RUN. 2 file(s) would change. Re-run with --apply.",
    "",
)


@pytest.mark.parametrize(("entries", "keeps", "expected"), [
    pytest.param(RETARGETS, ["pkg/held.py:3"], (0, IMPORTS_OUT, []), id="held"),
    pytest.param([*RETARGETS, *TARGET_RENAMES], ["pkg/held.py:3"], (1, "", [
        message("refactor.map-conflict", path="pkg/use.py", line=2, first=1, second=3),
        message("refactor.map-conflict", path="pkg/use.py", line=3, first=2, second=4),
    ]), id="owners"),
    pytest.param(RETARGETS, ["pkg/held.py:3", "pkg/compat.py:1"], (2, "", [
        message("refactor.keep-unmatched", site="pkg/compat.py:1"),
    ]), id="keep-unmatched"),
])
def test_retarget_imports_and_keeps_are_planned_as_one_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
    entries: list[dict[str, object]], keeps: list[str], expected: tuple[int, str, list[str]],
) -> None:
    root = _project(tmp_path, IMPORTS, entries)
    flags = [arg for keep in keeps for arg in ("--keep", keep)]
    code, out, err = run(root, ["rename-map", "map.yaml", *flags], monkeypatch, capsys)
    actual = (code, out, err.splitlines())
    assert actual == expected


def test_no_import_need_outlives_the_import_plan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _project(tmp_path, IMPORTS, RETARGETS)
    lifetimes = Lifetimes(monkeypatch)

    def tracked_plan(session: object, needs: list[ImportNeed]) -> object:
        for need in needs:
            lifetimes.refs["need"].append(weakref.ref(need))
            nodes: list[object] = [need.anchor, *([need.leaving] if need.leaving is not None else []), *need.duplicates]
            lifetimes.refs["node"] += [weakref.ref(node) for node in nodes]
        return plan_imports(session, needs)  # pyright: ignore[reportArgumentType]

    monkeypatch.setattr(rename_map, "plan_imports", tracked_plan)
    code, out, err = run(root, ["rename-map", "map.yaml"], monkeypatch, capsys)
    assert (code, err) == (0, ""), out
    assert lifetimes.at_report == {"need": 0, "node": 0}


class Exports:
    """The language servers started and the exports made once the `conflicts` phase is announced."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.conflicts: bool = False
        self.starts: int = 0
        self.requests: list[ExportRequest] = []
        phase, enter, export = Progress.phase, LanguageServer.__enter__, LanguageServer.export

        def announced(progress: Progress, name: str) -> None:
            self.conflicts = self.conflicts or name == "conflicts"
            phase(progress, name)

        def entered(server: LanguageServer) -> LanguageServer:
            self.starts += self.conflicts
            return enter(server)

        def exported(server: LanguageServer, request: ExportRequest) -> OccurrenceIndex:
            if self.conflicts:
                self.requests.append(request)
            return export(server, request)

        monkeypatch.setattr(Progress, "phase", announced)
        monkeypatch.setattr(LanguageServer, "__enter__", entered)
        monkeypatch.setattr(LanguageServer, "export", exported)


STORE = "class Store:\n    def load(self) -> int:\n        return 1\n"
LIGATURE = "\ufb01eld"
NFKC_CASES = [
    pytest.param(LIGATURE, "field", id="new-name-spelled-by-nfkc"),
    pytest.param("field", LIGATURE, id="declared-name-spelled-by-nfkc"),
]


def _nfkc_project(tmp_path: Path, new: str, declared: str) -> Path:
    other = f"from pkg.store import Store\n\n\nclass Sub(Store):\n    def {declared}(self) -> int:\n        return 2\n"
    return _project(tmp_path, {"pkg/store.py": STORE, "pkg/other.py": other},
                    [{"file": "pkg/store.py", "symbol": "Store.load", "new_name": new}])


@pytest.mark.parametrize(("new", "declared"), NFKC_CASES)
def test_a_class_fact_missed_after_rules_is_exported_by_a_fresh_server(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], new: str, declared: str
) -> None:
    root = _nfkc_project(tmp_path, new, declared)
    exports = Exports(monkeypatch)
    code, out, err = run(root, ["rename-map", "map.yaml"], monkeypatch, capsys)
    assert (code, out, err) == (1, "", message("refactor.name-conflict", name=new, path="pkg/other.py", line=5) + "\n")
    assert exports.starts == 1
    assert [[(q.path.name, q.kinds) for q in r.facts] for r in exports.requests] == [[("other.py", ("class",))]]
    assert [r.members for r in exports.requests] == [["field"]]


def test_a_server_failure_on_a_missed_class_fact_refuses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _nfkc_project(tmp_path, LIGATURE, "field")
    missing = str(tmp_path / "no-such-node")
    rules = RenameMap.rules

    def failing_after_rules(engine: RenameMap, *args: object) -> object:
        try:
            return rules(engine, *args)  # pyright: ignore[reportArgumentType]
        finally:
            monkeypatch.setattr(language_server, "_bundled_command", lambda: [missing, "--stdio"])

    monkeypatch.setattr(RenameMap, "rules", failing_after_rules)
    code, out, err = run_raw(root, ["rename-map", "map.yaml"], monkeypatch, capsys)
    cause = message("refactor.checker-not-started", error=f"{missing}: no such file or directory")
    assert (code, out, final_report(err)) == (1, "", f"{message('refactor.pyright-failed')}\n{cause}\n")


def test_a_class_fact_merged_before_rules_needs_no_export(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _project(tmp_path, {"pkg/store.py": STORE + "\n    def fetch(self) -> int:\n        return 2\n"},
                    [{"file": "pkg/store.py", "symbol": "Store.load", "new_name": "fetch"}])
    exports = Exports(monkeypatch)
    code, out, err = run(root, ["rename-map", "map.yaml"], monkeypatch, capsys)
    assert (code, out, err) == (1, "", message("refactor.name-conflict", name="fetch", path="pkg/store.py", line=5) + "\n")
    assert (exports.starts, exports.requests) == (0, [])


CLASS_A = "class A:\n    pass\n"
CLASS_B = "from pkg.a import A\n\n\nclass B(A):\n    pass\n"


def _class_index(tmp_path: Path) -> tuple[Session, ServerSession, RunIndex]:
    """A run's index over `pkg/a.py` (class A merged) and `pkg/b.py` (class B, a subclass, not merged), exported."""
    session = Session(write_project(tmp_path / "proj", {"pkg/a.py": CLASS_A, "pkg/b.py": CLASS_B}))
    server = ServerSession(session.root, session.read)
    index = RunIndex(session.root, session.load, server, IndexCache(session.root))
    _ = index.prepare({"A"}, [session.root / "pkg/a.py"], members=["x"])
    index.build()
    return session, server, index


def _exports(monkeypatch: pytest.MonkeyPatch) -> list[ExportRequest]:
    requests: list[ExportRequest] = []
    export = LanguageServer.export

    def recorded(server: LanguageServer, request: ExportRequest) -> OccurrenceIndex:
        requests.append(request)
        return export(server, request)

    monkeypatch.setattr(LanguageServer, "export", recorded)
    return requests


def test_the_class_fact_source_answers_a_merged_fact_without_a_server(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session, server, index = _class_index(tmp_path)
    expected = index.class_facts(session.root / "pkg/a.py", CLASS_A.index("A"))
    source = index.class_fact_source()  # pyright: ignore[reportAttributeAccessIssue]
    index.close()
    server.close()
    requests = _exports(monkeypatch)
    assert source.class_facts(session.root / "pkg/a.py", CLASS_A.index("A")) == expected
    assert (requests, server.started) == ([], False)


def test_the_class_fact_source_exports_a_miss_through_a_fresh_server(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session, server, index = _class_index(tmp_path)
    source = index.class_fact_source()  # pyright: ignore[reportAttributeAccessIssue]
    index.close()
    server.close()
    requests = _exports(monkeypatch)
    b = session.root / "pkg/b.py"
    try:
        found = source.class_facts(b, CLASS_B.index("B("))
        assert server.started
    finally:
        server.close()
    assert [(r.members, r.facts) for r in requests] == [
        (["x"], [FactQuery(path=b, offset=CLASS_B.index("B("), kinds=("class",))])]
    assert (session.root / "pkg/a.py", CLASS_A.index("A")) in {(s.path, s.start) for s in found.ancestors}


def test_the_class_fact_source_keeps_no_index(tmp_path: Path) -> None:
    _session, server, index = _class_index(tmp_path)
    source = index.class_fact_source()  # pyright: ignore[reportAttributeAccessIssue]
    index.close()
    server.close()
    ref = weakref.ref(index)
    del index
    _ = gc.collect()
    assert (ref(), source is not None) == (None, True)


MODULE_FILES = {
    "pkg/client.py": "def connect() -> int:\n    return 1\n",
    "pkg/use.py": "from pkg import client\nfrom pkg.client import connect\n\nx = client.connect() + connect()\n",
}
MODULE_ENTRY = {"file": "pkg/use.py", "symbol": "client", "new_name": "session"}
MODULE_DIFF = (
    "rename from pkg/client.py",
    "rename to pkg/session.py",
)
USE_DIFF = (
    "--- a/pkg/use.py",
    "+++ b/pkg/use.py",
    "@@ -1,4 +1,4 @@",
    "-from pkg import client",
    "-from pkg.client import connect",
    "+from pkg import session",
    "+from pkg.session import connect",
    " ",
    "-x = client.connect() + connect()",
    "+x = session.connect() + connect()",
    "",
)
STORE_USE = STORE + "\n\ndef use(s: Store) -> int:\n    return s.load()\n"
STORE_DIFF = (
    "--- a/pkg/store.py",
    "+++ b/pkg/store.py",
    "@@ -1,7 +1,7 @@",
    " class Store:",
    "-    def load(self) -> int:",
    "+    def fetch(self) -> int:",
    "         return 1",
    " ",
    " ",
    " def use(s: Store) -> int:",
    "-    return s.load()",
    "+    return s.fetch()",
    "",
)


@pytest.mark.parametrize(("files", "entries", "expected"), [
    pytest.param(MODULE_FILES, [MODULE_ENTRY], _lines(
        "Renaming <client> to <session>:", "", "", *MODULE_DIFF, *USE_DIFF, "", "",
        "DRY-RUN. 2 file(s) would change. Re-run with --apply.", "",
    ), id="alone"),
    pytest.param({**MODULE_FILES, "pkg/store.py": STORE_USE},
                 [MODULE_ENTRY, {"file": "pkg/store.py", "symbol": "Store.load", "new_name": "fetch"}], _lines(
        "Renaming <client> to <session>:", "Renaming <load> to <fetch>:", "", "", *MODULE_DIFF, *STORE_DIFF,
        *USE_DIFF, "", "", "DRY-RUN. 3 file(s) would change. Re-run with --apply.", "",
    ), id="beside-a-symbol-rename"),
])
def test_a_module_entry_leaves_no_worker_or_locator_alive_at_the_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], files: dict[str, str],
    entries: list[dict[str, object]], expected: str,
) -> None:
    root = _project(tmp_path, files, entries)
    lifetimes = Lifetimes(monkeypatch)
    lifetimes.workers()
    lifetimes.track(EntryLocator, lambda _: "locator")
    assert run(root, ["rename-map", "map.yaml"], monkeypatch, capsys) == (0, expected, "")
    assert lifetimes.at_report == {"worker": 0, "locator": 0}
