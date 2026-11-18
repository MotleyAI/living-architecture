"""The name-conflict check re-parses and re-judges only the files whose edits can change a name's meaning, and finds
every conflict the full check finds."""

from __future__ import annotations

import gc
import re
import weakref
from collections import Counter
from pathlib import Path

import pytest

from living_architecture.contract import message
from living_architecture.refactor import bindings
from living_architecture.refactor.bindings import BindingCheck, Conflict, EntryEdits
from living_architecture.refactor.locators import RefactorError
from living_architecture.refactor.python_source import SourceFile
from living_architecture.refactor.text_edits import TextEdit, apply_edits

NEW = "fresh"


def _check(files: dict[str, str]) -> BindingCheck:
    sources = {rel: SourceFile(Path(rel), text) for rel, text in files.items()}
    return BindingCheck(sorted(files), [""], sources.__getitem__)


def _one(check: BindingCheck, entries: list[EntryEdits], moves: dict[str, str] | None = None) -> list[Conflict]:
    """The conflicts of a one-pass plan."""
    [found] = check.conflicts([entries], moves)
    return found


def _found(files: dict[str, str], entries: list[EntryEdits]) -> set[tuple[tuple[str, int], str]]:
    """The distinct sites and names the check finds."""
    return {(c.site, c.name) for c in _one(_check(files), entries)}


def _renamed(files: dict[str, str], rel: str, old: str = "old", new: str = NEW) -> list[TextEdit]:
    """Edits renaming each `old` of `rel` that is a name, not an attribute, to `new`."""
    found = list(re.finditer(rf"(?<![\w.]){re.escape(old)}(?!\w)", files[rel]))
    return [TextEdit(path=rel, start=m.start(), end=m.end(), new_text=new) for m in found]


def _at(files: dict[str, str], rel: str, needle: str, nth: int = 0) -> tuple[str, int]:
    offset = -1
    for _ in range(nth + 1):
        offset = files[rel].index(needle, offset + 1)
    return rel, offset


def _edit(files: dict[str, str], rel: str, needle: str, new_text: str, nth: int = 0) -> TextEdit:
    _, start = _at(files, rel, needle, nth)
    return TextEdit(path=rel, start=start, end=start + len(needle), new_text=new_text)


def _member(files: dict[str, str], rel: str, dotted: str, new_text: str) -> TextEdit:
    """An edit of the attribute name of the first `dotted` of `rel`."""
    _, start = _at(files, rel, dotted)
    start += dotted.rindex(".") + 1
    return TextEdit(path=rel, start=start, end=start + len(dotted) - dotted.rindex(".") - 1, new_text=new_text)


class _Parses:
    """Counts each analysis of a module text by path, split into the text before the edits and an edited one."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, files: dict[str, str]) -> None:
        self.before: Counter[str] = Counter()
        self.after: Counter[str] = Counter()
        real = bindings._Parsed.__init__
        parses = self

        def counting(self: bindings._Parsed, source: SourceFile, *args: object, **kwargs: object) -> None:
            rel = source.path.as_posix()
            (parses.before if files.get(rel) == source.text else parses.after)[rel] += 1
            real(self, source, *args, **kwargs)  # pyright: ignore[reportArgumentType]

        monkeypatch.setattr(bindings._Parsed, "__init__", counting)

    def reset(self) -> None:
        self.before.clear()
        self.after.clear()


# A module state after edits: its path and its edited text.
State = tuple[str, str]


class _Alive:
    """Weak references to each after-edit state and the pass whose judging built it."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, files: dict[str, str]) -> None:
        self.refs: dict[State, weakref.ref[bindings._Parsed]] = {}
        self.built: dict[State, int] = {}
        self.judged = 0
        real_init, real_judge = bindings._Parsed.__init__, bindings._Judge.conflicts
        alive = self

        def recording(self: bindings._Parsed, source: SourceFile, *args: object, **kwargs: object) -> None:
            real_init(self, source, *args, **kwargs)  # pyright: ignore[reportArgumentType]
            state = (source.path.as_posix(), source.text)
            if files.get(state[0]) != state[1]:
                alive.refs[state] = weakref.ref(self)
                alive.built[state] = alive.judged

        def judging(self: bindings._Judge, checked: list[str]) -> list[Conflict]:
            alive.judged += 1
            return real_judge(self, checked)

        monkeypatch.setattr(bindings._Parsed, "__init__", recording)
        monkeypatch.setattr(bindings._Judge, "conflicts", judging)

    def now(self) -> set[State]:
        gc.collect()
        return {state for state, ref in self.refs.items() if ref() is not None}


# --- conflicts the narrowing must keep -------------------------------------------------------------------------------


def test_a_class_body_declaration_renamed_onto_an_existing_one() -> None:
    files = {"pkg/m.py": "class C:\n    old = 1\n    fresh = 2\n"}
    edits = _renamed(files, "pkg/m.py")
    assert _found(files, [EntryEdits(index=1, new_name=NEW, edits=edits)]) == {(_at(files, "pkg/m.py", "fresh"), NEW)}


def test_a_renamed_global_seen_through_a_star_import_in_an_unedited_file() -> None:
    files = {
        "pkg/a.py": "old = 1\nprint(old)\n",
        "pkg/b.py": "fresh = 0\n",
        "pkg/u.py": "from pkg.b import *\nfrom pkg.a import *\n\nprint(fresh)\n",
    }
    edits = _renamed(files, "pkg/a.py")
    assert _found(files, [EntryEdits(index=1, new_name=NEW, edits=edits)]) == {(_at(files, "pkg/u.py", "fresh"), NEW)}


def test_a_renamed_global_seen_through_a_two_step_star_chain() -> None:
    files = {
        "pkg/a.py": "old = 1\nprint(old)\n",
        "pkg/b.py": "fresh = 0\n",
        "pkg/m.py": "from pkg.a import *\n",
        "pkg/u.py": "from pkg.b import *\nfrom pkg.m import *\n\nprint(fresh)\n",
    }
    edits = _renamed(files, "pkg/a.py")
    assert _found(files, [EntryEdits(index=1, new_name=NEW, edits=edits)]) == {(_at(files, "pkg/u.py", "fresh"), NEW)}


def test_an_edited_all_changes_what_a_star_import_binds() -> None:
    files = {
        "pkg/a.py": 'old = 1\nfresh = 2\n__all__ = ["old"]\n',
        "pkg/b.py": "fresh = 0\n",
        "pkg/u.py": "from pkg.b import *\nfrom pkg.a import *\n\nprint(fresh)\n",
    }
    edits = [_edit(files, "pkg/a.py", "old", NEW, nth=1)]
    assert _found(files, [EntryEdits(index=1, new_name=NEW, edits=edits)]) == {(_at(files, "pkg/u.py", "fresh"), NEW)}


RETARGET = {
    "pkg/core.py": "class Model:\n    pass\n",
    "pkg/compat.py": "from pkg.core import Model\n\nAcmeModel = Model\n",
}


def _retarget(files: dict[str, str]) -> EntryEdits:
    """`AcmeModel` retargeted to `Model` in `pkg/use.py`: its import replaced by one of the target, its uses rewritten."""
    added = _edit(files, "pkg/use.py", "from pkg.compat import AcmeModel", "from pkg.core import Model")
    uses = _renamed(files, "pkg/use.py", "AcmeModel", "Model")[1:]
    return EntryEdits(index=1, new_name="Model", edits=[added, *uses], target="Model", binds=[added])


def test_a_retargets_added_import_means_the_target() -> None:
    files = {**RETARGET, "pkg/use.py": "from pkg.compat import AcmeModel\n\nx = AcmeModel()\n"}
    assert _found(files, [_retarget(files)]) == set()


def test_a_file_with_an_attribute_edit_and_a_name_edit() -> None:
    files = {"pkg/m.py": "old = 1\n\n\ndef f(c: object) -> int:\n    fresh = 2\n    return c.old + old + fresh\n"}
    attribute = _member(files, "pkg/m.py", "c.old", NEW)
    entries = [EntryEdits(index=1, new_name=NEW, edits=[attribute]),
               EntryEdits(index=2, new_name=NEW, edits=_renamed(files, "pkg/m.py"))]
    assert _found(files, entries) == {(_at(files, "pkg/m.py", "fresh = 2"), NEW)}


def test_a_length_changing_attribute_edit_before_a_binding_edit_maps_back() -> None:
    files = {"pkg/m.py": "old = 1\n\n\ndef f(c: object) -> int:\n    v = c.a\n    fresh = 2\n    return old + fresh + v\n"}
    attribute = _member(files, "pkg/m.py", "c.a", "a_much_longer_attribute")
    entries = [EntryEdits(index=1, new_name="a_much_longer_attribute", edits=[attribute]),
               EntryEdits(index=2, new_name=NEW, edits=_renamed(files, "pkg/m.py"))]
    assert _found(files, entries) == {(_at(files, "pkg/m.py", "fresh = 2"), NEW)}


# --- what is re-parsed and re-judged ---------------------------------------------------------------------------------

INERT = {
    "pkg/m.py": "old = 1\nprint(old)\n",
    "pkg/attr.py": "def g(c: object) -> object:\n    return c.old\n",
    "pkg/kw.py": "def h(**kw: int) -> None:\n    pass\n\n\nh(old=1)\n",
}


def test_a_file_whose_only_edits_are_attribute_or_keyword_names_is_not_re_parsed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parses = _Parses(monkeypatch, INERT)
    edits = [*_renamed(INERT, "pkg/m.py"), _member(INERT, "pkg/attr.py", "c.old", NEW),
             _edit(INERT, "pkg/kw.py", "old", NEW)]
    assert _one(_check(INERT), [EntryEdits(index=1, new_name=NEW, edits=edits)]) == []
    assert (parses.after["pkg/m.py"], parses.after["pkg/attr.py"], parses.after["pkg/kw.py"]) == (1, 0, 0)


def test_the_all_together_pass_reuses_each_single_entry_state(monkeypatch: pytest.MonkeyPatch) -> None:
    files = {"pkg/a.py": "old = 1\nprint(old)\n", "pkg/b.py": "other = 2\nprint(other)\n"}
    first = EntryEdits(index=1, new_name=NEW, edits=_renamed(files, "pkg/a.py"))
    second = EntryEdits(index=2, new_name="next", edits=_renamed(files, "pkg/b.py", "other", "next"))
    parses = _Parses(monkeypatch, files)
    passes = _check(files).conflicts([[first], [second], [first, second]])
    assert next(passes) == next(passes) == []
    parses.reset()
    assert next(passes) == []
    assert parses.after == Counter()
    assert next(passes, None) is None


def test_two_passes_with_the_same_edits_of_a_file_build_its_state_once(monkeypatch: pytest.MonkeyPatch) -> None:
    files = {"pkg/a.py": "old = 1\nprint(old)\n", "pkg/b.py": "other = 2\nprint(other)\n",
             "pkg/c.py": "shared = 3\nprint(shared)\n"}
    common = _renamed(files, "pkg/c.py", "shared", "common")
    first = EntryEdits(index=1, new_name=NEW, edits=[*_renamed(files, "pkg/a.py"), *common])
    second = EntryEdits(index=2, new_name="later", edits=[*_renamed(files, "pkg/b.py", "other", "later"), *common])
    parses = _Parses(monkeypatch, files)
    assert list(_check(files).conflicts([[first], [second]])) == [[], []]
    assert parses.after == Counter({"pkg/a.py": 1, "pkg/b.py": 1, "pkg/c.py": 1})


# --- how long an after-edit state lives ------------------------------------------------------------------------------

LIVE = {
    "pkg/a.py": "old = 1\nprint(old)\n",
    "pkg/b.py": "other = 2\nprint(other)\n",
    "pkg/c.py": "old = 3\nother = 4\nprint(old, other)\n",
}


def _live_entries() -> tuple[EntryEdits, EntryEdits]:
    """Entry 1 edits `a` and `c`, entry 2 edits `b` and `c`."""
    first = EntryEdits(index=1, new_name=NEW, edits=[*_renamed(LIVE, "pkg/a.py"), *_renamed(LIVE, "pkg/c.py")])
    second = EntryEdits(index=2, new_name="later", edits=[*_renamed(LIVE, "pkg/b.py", "other", "later"),
                                                          *_renamed(LIVE, "pkg/c.py", "other", "later")])
    return first, second


def _after(rel: str, *entries: EntryEdits) -> State:
    return rel, apply_edits(LIVE[rel], sorted((e for entry in entries for e in entry.edits if e.path == rel),
                                              key=lambda e: e.start))


def test_an_after_state_lives_until_the_last_pass_reading_it(monkeypatch: pytest.MonkeyPatch) -> None:
    first, second = _live_entries()
    alive = _Alive(monkeypatch, LIVE)
    a1, b2 = _after("pkg/a.py", first), _after("pkg/b.py", second)
    passes = _check(LIVE).conflicts([[first], [second], [first, second]])
    assert next(passes) == []
    assert alive.now() == {a1}
    assert next(passes) == []
    assert alive.now() == {a1, b2}
    assert {_after("pkg/c.py", first), _after("pkg/c.py", second)} <= alive.built.keys()
    assert next(passes) == []
    assert alive.now() == set()
    assert [state for state, n in alive.built.items() if n == 3] == [_after("pkg/c.py", first, second)]
    assert next(passes, None) is None


def test_without_the_all_entries_pass_no_after_state_outlives_its_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    first, second = _live_entries()
    alive = _Alive(monkeypatch, LIVE)
    passes = _check(LIVE).conflicts([[first], [second]])
    assert next(passes) == []
    assert alive.built.keys() == {_after("pkg/a.py", first), _after("pkg/c.py", first)}
    assert alive.now() == set()
    assert next(passes) == []
    assert len(alive.built) == 4
    assert alive.now() == set()


def test_a_pass_is_yielded_before_a_later_pass_parses_its_after_states() -> None:
    files = {"pkg/a.py": "old = 1\nprint(old)\n", "pkg/b.py": "other = 2\nprint(other)\n"}
    first = EntryEdits(index=1, new_name=NEW, edits=_renamed(files, "pkg/a.py"))
    broken = EntryEdits(index=2, new_name="later", edits=[_edit(files, "pkg/b.py", "other", "later(")])
    passes = _check(files).conflicts([[first], [broken]])
    assert next(passes) == []
    with pytest.raises(RefactorError, match=re.escape(message("refactor.cannot-rename"))):
        next(passes)


def test_a_pass_without_names_yields_no_conflicts_in_its_place() -> None:
    files = {"pkg/m.py": "class C:\n    old = 1\n    fresh = 2\n"}
    empty = EntryEdits(index=1, new_name=NEW, edits=[])
    entry = EntryEdits(index=2, new_name=NEW, edits=_renamed(files, "pkg/m.py"))
    alone = _one(_check(files), [entry])
    assert alone
    assert list(_check(files).conflicts([[empty], [entry]])) == [[], alone]


def test_an_unedited_file_without_a_star_import_of_an_edited_one_is_not_judged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    files = {"pkg/a.py": "old = 1\nprint(old)\n", "pkg/other.py": "fresh = 2\nprint(fresh)\n"}
    parses = _Parses(monkeypatch, files)
    assert _one(_check(files), [EntryEdits(index=1, new_name=NEW, edits=_renamed(files, "pkg/a.py"))]) == []
    assert parses.before["pkg/other.py"] == 0


def test_a_run_moving_files_re_judges_every_file(monkeypatch: pytest.MonkeyPatch) -> None:
    files = {
        "pkg/a.py": "x = 1\n",
        "pkg/use.py": "from pkg import a\n\nprint(a.x)\n",
        "pkg/other.py": "b = 1\nprint(b)\n",
    }
    parses = _Parses(monkeypatch, files)
    edits = _renamed(files, "pkg/use.py", "a", "b")
    conflicts = _one(_check(files), [EntryEdits(index=1, new_name="b", edits=edits)], {"pkg/a.py": "pkg/b.py"})
    assert conflicts == []
    assert parses.before["pkg/other.py"] >= 1


@pytest.mark.parametrize(
    ("text", "needle"),
    [('s = "old"\nprint(s)\n', "old"), ("# old\nprint(1)\n", "old"), ('y: "old" = 1\nprint(y)\n', "old")],
    ids=["string", "comment", "string-annotation"],
)
def test_a_file_whose_only_edit_is_another_kind_is_re_parsed(
    monkeypatch: pytest.MonkeyPatch, text: str, needle: str
) -> None:
    files = {"pkg/m.py": "old = 1\nprint(old)\n", "pkg/x.py": text}
    parses = _Parses(monkeypatch, files)
    edits = [*_renamed(files, "pkg/m.py"), _edit(files, "pkg/x.py", needle, NEW)]
    assert _one(_check(files), [EntryEdits(index=1, new_name=NEW, edits=edits)]) == []
    assert parses.after["pkg/x.py"] == 1


def test_a_renamed_string_annotation_captured_by_a_local() -> None:
    text = 'class old:\n    pass\n\n\ndef f() -> None:\n    fresh = 1\n    x: "old" = None\n    print(x, fresh)\n'
    files = {"pkg/m.py": text}
    edits = [_edit(files, "pkg/m.py", "old", NEW), _edit(files, "pkg/m.py", 'old"', f'{NEW}"')]
    assert _found(files, [EntryEdits(index=1, new_name=NEW, edits=edits)]) == {(_at(files, "pkg/m.py", "fresh = 1"), NEW)}
