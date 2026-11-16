"""The export's seams: a run's index is the same exported in one request or in two merged, and the export's follow
guard leaves a cold and a warm run agreeing on the facts a rule fetches on demand."""

from __future__ import annotations

import re
import sys
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from project_files import write_project
from refactor_cli import run_raw
from typing_extensions import override

from living_architecture.lang import (
    ExportRequest,
    LanguageServer,
    Occurrence,
    OccurrenceIndex,
    PositionFacts,
    Span,
)
from living_architecture.refactor.occurrence_index import RunIndex, ServerSession
from living_architecture.refactor.python_source import SourceFile

BASE = "from pydantic import BaseModel\n\n\nclass Base(BaseModel):\n    name: str\n\n\nclass Tagged(Base):\n    tag: str\n"
A = ("from pkg.base import Base, Tagged\n\n\nclass A(Tagged):\n    name: str\n\n\n"
     "def make() -> A:\n    return A(name=\"a\", tag=\"t\")\n\n\nfirst = Base(name=\"x\")\n")
B = ("from pkg.base import Base\n\n\nclass B(Base):\n    size: int\n\n\n"
     "def build() -> B:\n    return B(name=\"b\", size=1)\n")
FILES = {"pkg/base.py": BASE, "pkg/a.py": A, "pkg/b.py": B}
NAMES = {"name", "tag"}
HALVES = (["pkg/a.py"], ["pkg/b.py", "pkg/base.py"])
_DEFINITION = re.compile(r"^\s*(?:class|def) (\w+)|^(\w+)\s*[:=]", re.MULTILINE)
_BASES = re.compile(r"^class \w+\(([\w, ]+)\)", re.MULTILINE)


class _FakeServer(LanguageServer):
    """An in-process stand-in for the export: occurrences by whole word, definitions by the first declaration of the
    word across the project, and, as the real export follows, the bases of every class a definition lands on."""

    def __init__(self, root: Path) -> None:
        super().__init__(root, command=["unused"])
        self.root = root
        self.exports: list[OccurrenceIndex] = []

    @override
    def open(self, path: Path, text: str) -> None:
        pass

    @override
    def change(self, path: Path, text: str) -> None:
        pass

    def _files(self) -> list[Path]:
        return sorted(self.root.rglob("*.py"))

    def _word(self, path: Path, offset: int) -> str:
        text = path.read_text(encoding="utf-8")
        found = re.compile(r"\w+").match(text, offset)
        return found.group() if found else ""

    def _declared(self, word: str) -> list[Span]:
        for path in self._files():
            for m in _DEFINITION.finditer(path.read_text(encoding="utf-8")):
                group = 1 if m.group(1) else 2
                if m.group(group) == word:
                    return [Span(path=path, start=m.start(group), end=m.end(group))]
        return []

    def _fake_facts(self, path: Path, offset: int, kinds: tuple[Any, ...]) -> PositionFacts:
        found = tuple(self._declared(self._word(path, offset)))
        return PositionFacts(path=path, offset=offset, kinds=kinds, definition=found if "definition" in kinds else (),
                             type_definition=found if "typeDefinition" in kinds else ())

    def _follow(self, answers: list[PositionFacts]) -> list[PositionFacts]:
        out: list[PositionFacts] = []
        seen: set[tuple[Path, int]] = set()
        frontier = [d for a in answers for d in (*a.definition, *a.type_definition)]
        while frontier:
            span = frontier.pop(0)
            text = span.path.read_text(encoding="utf-8")
            for m in _BASES.finditer(text):
                if m.start(0) + len("class ") != span.start:
                    continue
                for base in re.finditer(r"\w+", m.group(1)):
                    key = (span.path, m.start(1) + base.start())
                    if key not in seen:
                        seen.add(key)
                        facts = self._fake_facts(span.path, key[1], ("definition",))
                        out.append(facts)
                        frontier.extend(facts.definition)
        return out

    @override
    def export(self, request: ExportRequest) -> OccurrenceIndex:
        occurrences = [
            Occurrence(span=Span(path=path, start=m.start(), end=m.end()), name=name, kind="name")
            for path in request.files
            for name in request.names
            for m in re.finditer(rf"(?<!\w){re.escape(name)}(?!\w)", path.read_text(encoding="utf-8"))
        ]
        answers = [self._fake_facts(q.path, q.offset, q.kinds) for q in request.facts]
        found = OccurrenceIndex(occurrences=occurrences, answers=answers, followed=self._follow(answers))
        self.exports.append(found)
        return found


class _FakeSession(ServerSession):
    def __init__(self, root: Path) -> None:
        super().__init__(root, lambda p: p.read_text(encoding="utf-8"))
        self.fake = _FakeServer(root)

    @override
    def get(self) -> LanguageServer:
        return self.fake


def _source(path: Path) -> SourceFile | None:
    return SourceFile(path, path.read_text(encoding="utf-8")) if path.is_file() else None


def _index(root: Path, session: ServerSession, halves: tuple[list[str], ...]) -> RunIndex:
    index = RunIndex(root, _source, session, None)
    for half in halves:
        index.prepare(NAMES, [root / rel for rel in half])
        index.build()
    return index


def _lookups(index: RunIndex) -> dict[str, Callable[[PositionFacts], object]]:
    return {
        "definition": lambda f: index.definition(f.path, f.offset),
        "typeDefinition": lambda f: index.type_definition(f.path, f.offset),
        "verdict": lambda f: index.verdict(f.path, f.offset),
        "access": lambda f: index.receiver(f.path, "", f.offset),
    }


def _state(index: RunIndex, root: Path, positions: list[PositionFacts]) -> dict[object, object]:
    """Every occurrence of the names in every file, and every fact the one-request export holds, as `index` answers."""
    out: dict[object, object] = {}
    for rel in FILES:
        for name in sorted(NAMES):
            out["occurrences", rel, name] = index.occurrences(root / rel, name)
    lookups = _lookups(index)
    for facts in positions:
        for kind in facts.kinds:
            out[kind, facts.path, facts.offset] = lookups[kind](facts)
    return out


def _positions(exports: list[OccurrenceIndex]) -> list[PositionFacts]:
    return [f for e in exports for f in (*e.answers, *e.followed)]


def test_two_requests_merged_give_the_one_request_index_through_the_fake(tmp_path: Path) -> None:
    root = write_project(tmp_path / "p", FILES)
    one_session, split_session = _FakeSession(root), _FakeSession(root)
    one = _index(root, one_session, (sorted(FILES),))
    split = _index(root, split_session, HALVES)
    positions = _positions(one_session.fake.exports)
    shared = {(f.path, f.offset) for e in split_session.fake.exports for f in e.followed}
    assert len(split_session.fake.exports) == 2
    assert any(f.path == root / "pkg/base.py" for f in positions)
    assert sum(len(e.followed) for e in split_session.fake.exports) > len(shared)
    def export_counts() -> tuple[int, int]:
        return len(one_session.fake.exports), len(split_session.fake.exports)

    exported = export_counts()
    assert _state(split, root, positions) == _state(one, root, positions)
    assert export_counts() == exported


class _Recorded:
    """The answers every real export of a test returns."""

    def __init__(self) -> None:
        self.exports: list[OccurrenceIndex] = []

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        export = LanguageServer.export

        def recording(server: LanguageServer, request: ExportRequest) -> OccurrenceIndex:
            found = export(server, request)
            self.exports.append(found)
            return found

        monkeypatch.setattr(LanguageServer, "export", recording)


@pytest.fixture
def real_sessions(tmp_path: Path) -> Iterator[tuple[Path, ServerSession, ServerSession]]:
    root = write_project(tmp_path / "p", FILES).resolve()
    sessions = (ServerSession(root, lambda p: p.read_text(encoding="utf-8")),
                ServerSession(root, lambda p: p.read_text(encoding="utf-8")))
    try:
        yield root, *sessions
    finally:
        for session in sessions:
            session.close()


@pytest.mark.integration
def test_two_requests_merged_give_the_one_request_index_through_basedpyright(
    real_sessions: tuple[Path, ServerSession, ServerSession], monkeypatch: pytest.MonkeyPatch
) -> None:
    root, one_session, split_session = real_sessions
    recorded = _Recorded()
    recorded.install(monkeypatch)
    one = _index(root, one_session, (sorted(FILES),))
    positions = _positions(recorded.exports)
    split = _index(root, split_session, HALVES)
    split_exports = recorded.exports[1:]
    assert len(split_exports) == 2
    assert any(d.path == root / "pkg/base.py" for f in split_exports[0].answers for d in f.definition)
    count = len(recorded.exports)
    assert _state(split, root, positions) == _state(one, root, positions)
    assert len(recorded.exports) == count


LIBRARY = "from pydantic import BaseModel\n\n\nclass LibModel(BaseModel):\n    ident: int = 0\n"
MODELS = "from extlib import LibModel\n\n\nclass Row(LibModel):\n    title: str\n"
USE = "from pkg.models import Row\n\nrow = Row(title=\"x\")\n"
RENAME = ["rename", "--file", "pkg/models.py", "--symbol", "Row.title", "--new-name", "heading"]
_LINKED = ("pydantic", "pydantic_core", "typing_extensions.py", "annotated_types", "typing_inspection")


def _library_venv(root: Path) -> Path:
    """A virtualenv holding `extlib`, whose `LibModel` subclasses pydantic's `BaseModel`, pydantic linked in."""
    site = root / "lib" / f"python3.{sys.version_info.minor}" / "site-packages"
    (site / "extlib").mkdir(parents=True)
    (site / "extlib" / "__init__.py").write_text(LIBRARY, encoding="utf-8")
    ours = Path(next(p for p in sys.path if p.endswith("site-packages") and (Path(p) / "pydantic").is_dir()))
    for name in _LINKED:
        (site / name).symlink_to(ours / name)
    (root / "pyvenv.cfg").write_text(f"home = /usr/bin\nversion = 3.{sys.version_info.minor}.0\n", encoding="utf-8")
    return root


class _Facts:
    """The facts a run's rules read from its index, and the exports and servers it asks for."""

    def __init__(self) -> None:
        self.read: dict[tuple[str, Path, int], object] = {}
        self.requests: list[ExportRequest] = []
        self.starts = 0

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for name in ("definition", "type_definition", "verdict"):
            self._record(monkeypatch, name)
        export, enter = LanguageServer.export, LanguageServer.__enter__

        def exporting(server: LanguageServer, request: ExportRequest) -> OccurrenceIndex:
            self.requests.append(request)
            return export(server, request)

        def starting(server: LanguageServer) -> LanguageServer:
            self.starts += 1
            return enter(server)

        monkeypatch.setattr(LanguageServer, "export", exporting)
        monkeypatch.setattr(LanguageServer, "__enter__", starting)

    def _record(self, monkeypatch: pytest.MonkeyPatch, name: str) -> None:
        lookup = getattr(RunIndex, name)

        def recording(index: RunIndex, path: Path, offset: int) -> object:
            found = lookup(index, path, offset)
            self.read[name, path, offset] = found
            return found

        monkeypatch.setattr(RunIndex, name, recording)


def _run(root: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> tuple[_Facts, Any]:
    facts = _Facts()
    with monkeypatch.context() as patched:
        facts.install(patched)
        result = run_raw(root, RENAME, patched, capsys)
    return facts, result


@pytest.mark.skipif(sys.platform == "win32", reason="the library is linked into the virtualenv")
def test_a_library_fact_fetched_on_demand_is_the_same_cold_and_warm(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    venv = _library_venv(tmp_path / "venvs" / "v")
    config = f'{{"venvPath": "{venv.parent}", "venv": "{venv.name}"}}\n'
    root = write_project(tmp_path / "proj", {"pyrightconfig.json": config, "pkg/models.py": MODELS, "pkg/use.py": USE},
                         venv=False).resolve()
    cold, cold_result = _run(root, monkeypatch, capsys)
    on_demand = [q for r in cold.requests if not r.names for q in r.facts if not q.path.is_relative_to(root)]
    assert on_demand, cold.requests
    assert cold_result[0] == 0, cold_result
    assert 'Row(heading="x")' in cold_result[1]
    warm, warm_result = _run(root, monkeypatch, capsys)
    assert warm_result == cold_result
    assert warm.read == cold.read
    assert (warm.starts, warm.requests) == (0, [])
