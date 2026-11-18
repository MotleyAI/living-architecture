"""Python renames through `**kwargs` carriers: the verdict of each carrier decides its call keywords and key strings."""

from __future__ import annotations

from pathlib import Path
from string import Template

import pytest
import yaml
from project_files import file_tree, write_project
from refactor_cli import entry_refusal, read, run

from living_architecture.contract import message

MODELS = """\
from typing import Any

from pydantic import BaseModel


class Query(BaseModel):
    source_model: str = "orders"
    measures: list[str] = []


class Other(BaseModel):
    measures: list[int] = []


def build(data: dict[str, Any]) -> Query:
    return Query(**data)
"""
WITHOUT_OTHER = ("--without", "pkg/q.py:12")

# One carrier per line of CALLS, by the verdict its name states.
CARRIERS = """\
from typing import Any

from pkg.q import Other, Query, build


def renamed_one(**kw: Any) -> Query:
    if kw and len(kw) > 1:
        print("many")
    return Query(**kw)


def renamed_two(**kw: Any) -> list[Query]:
    return [Query(**kw), Query.model_construct(**kw), Query.model_validate(kw), Query().model_copy(update=kw)]


def renamed_chain(**kw: Any) -> Query:
    return renamed_one(**kw)


async def renamed_async(**kw: Any) -> Query:
    return Query(**kw)


def other_one(**kw: Any) -> Other:
    return Other(**kw)


def other_chain(**kw: Any) -> Other:
    return other_one(**kw)


def other_own_parameter(measures: int = 0, **kw: Any) -> Query:
    print(measures)
    return Query(**kw)


def other_no_sink(**kw: Any) -> int:
    return len(kw)


def mixed_sinks(**kw: Any) -> tuple[Query, Other]:
    return Query(**kw), Other(**kw)


def mixed_chain(**kw: Any) -> object:
    return renamed_one(**kw), other_one(**kw)


def unresolved_use(**kw: Any) -> Query:
    return build(kw)


def unresolved_chain(**kw: Any) -> Query:
    return unresolved_use(**kw)


def unresolved_with_other(**kw: Any) -> object:
    return other_one(**kw), unresolved_use(**kw)


def unresolved_cycle_a(**kw: Any) -> Query:
    return unresolved_cycle_b(**kw)


def unresolved_cycle_b(**kw: Any) -> Query:
    return unresolved_cycle_a(**kw)


def unresolved_callee(factory: Any, **kw: Any) -> object:
    return factory(**kw)


def unresolved_keys(**kw: Any) -> Query:
    print(list(kw.keys()))
    return Query(**kw)


def unresolved_values(**kw: Any) -> Query:
    print(list(kw.values()))
    return Query(**kw)
"""
VERDICTS = ["renamed_one", "renamed_two", "renamed_chain", "renamed_async", "other_one", "other_chain", "other_own_parameter",
            "other_no_sink", "mixed_sinks", "mixed_chain", "unresolved_use", "unresolved_chain",
            "unresolved_with_other", "unresolved_cycle_a", "unresolved_cycle_b", "unresolved_callee", "unresolved_keys",
            "unresolved_values"]
CALLS = "from pkg import c\n\n\ndef use() -> None:\n" + "".join(
    f"    c.{name}({'None, ' if name == 'unresolved_callee' else ''}measures=[])\n" for name in VERDICTS)
FIRST_CALL = 5


def _unlinked(path: str, line: int, callee: str, old: str = "measures") -> str:
    return message("refactor.unlinked-keyword", path=path, line=line, callee=callee, old=old)


def _rename(symbol: str, new_name: str, *flags: str) -> list[str]:
    return ["--apply", "rename", "--file", "pkg/q.py", "--symbol", symbol, "--new-name", new_name, *flags]


def test_each_carrier_verdict_decides_its_call_keyword(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = write_project(tmp_path / "p", {"pkg/q.py": MODELS, "pkg/c.py": CARRIERS, "pkg/use.py": CALLS})
    argv = _rename("Query.measures", "metrics", *WITHOUT_OTHER, "--allow-blindspots")
    code, _out, err = run(root, argv, monkeypatch, capsys)
    assert code == 0
    listed = [name for name in VERDICTS if name.startswith(("mixed", "unresolved"))]
    assert err.splitlines() == [_unlinked("pkg/use.py", FIRST_CALL + VERDICTS.index(name), f"c.{name}")
                                for name in listed]
    expected = CALLS
    for name in VERDICTS:
        if name.startswith("renamed"):
            expected = expected.replace(f"c.{name}(measures=", f"c.{name}(metrics=")
    assert read(root, "pkg/use.py") == expected
    assert read(root, "pkg/c.py") == CARRIERS


def test_unlinked_carrier_keywords_refuse_the_rename(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = write_project(tmp_path / "p", {"pkg/q.py": MODELS, "pkg/c.py": CARRIERS, "pkg/use.py": CALLS})
    before = file_tree(root)
    code, out, err = run(root, _rename("Query.measures", "metrics", *WITHOUT_OTHER), monkeypatch, capsys)
    assert (code, out) == (1, "")
    assert err.splitlines()[-1] == message("refactor.blindspots", count=10, names="measures=")
    assert file_tree(root) == before


HELPER = """\
from typing import Any

from pydantic import BaseModel


class Query(BaseModel):
    source_model: str
    measures: list[str] = []


def q(**kw: Any) -> Query:
    kw.setdefault("source_model", "orders")
    return Query(**kw)


def test_it() -> None:
    assert q(measures=["n"]).source_model == "orders"
"""


def test_a_helper_building_a_model_carries_its_keyword_and_key_string(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = write_project(tmp_path / "p", {"pkg/q.py": HELPER})
    code, _out, err = run(root, _rename("Query.measures", "metrics"), monkeypatch, capsys)
    assert (code, err) == (0, "")
    assert read(root, "pkg/q.py") == HELPER.replace("measures", "metrics")
    code, _out, err = run(root, _rename("Query.source_model", "population"), monkeypatch, capsys)
    assert (code, err) == (0, "")
    assert read(root, "pkg/q.py") == HELPER.replace("measures", "metrics").replace("source_model", "population")


KEY_FORMS = """\
from typing import Any

from pydantic import BaseModel


class Query(BaseModel):
    source_model: str


def q(**kw: Any) -> Query:
    if "source_model" not in kw:
        kw["source_model"] = "orders"
    if kw.get("source_model") is None:
        del kw["source_model"]
    print(kw["source_model"], kw.pop("source_model", None), "source_model" in kw)
    return Query(**kw)
"""


def test_every_key_form_of_a_carrier_follows_the_field(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = write_project(tmp_path / "p", {"pkg/q.py": KEY_FORMS})
    code, _out, err = run(root, _rename("Query.source_model", "population"), monkeypatch, capsys)
    assert (code, err) == (0, "")
    assert read(root, "pkg/q.py") == KEY_FORMS.replace("source_model", "population")


ALIASED = Template("""\
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Query(BaseModel):
    model_config = ConfigDict($config)
    measures: list[str] = $default


def q(**kw: Any) -> Query:
    kw.setdefault("measures", [])
    print(kw["measures"], "measures" in kw)
    return Query(**kw)


def use() -> Query:
    return q(measures=["n"]) if q(**{"measures": []}) else q()
""")


@pytest.mark.parametrize(("config", "default"), [("", 'Field(default=[], alias="m")'), ("alias_generator=str.upper", "[]")],
                         ids=["alias", "alias-generator"])
def test_an_aliased_field_changes_no_carrier_keyword_key_or_key_string(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], config: str, default: str
) -> None:
    text = ALIASED.substitute(config=config, default=default)
    root = write_project(tmp_path / "p", {"pkg/q.py": text})
    code, _out, err = run(root, _rename("Query.measures", "metrics"), monkeypatch, capsys)
    leftovers = [message("refactor.leftover", path="pkg/q.py", line=line, where="string", old="measures") for line in (12, 13, 13)]
    assert (code, err.splitlines()) == (0, leftovers)
    assert read(root, "pkg/q.py") == text.replace("    measures: list[str]", "    metrics: list[str]")


SINK = """\
from typing import Any


def sink(*, old: int = 0, **rest: int) -> int:
    return old + len(rest)


def factory() -> Any:
    return object
"""
# Carriers whose flow of `old` or of `new` is unprovable, then one that only forwards.
UNPROVABLE = """\
from typing import Any

from pkg.s import factory, sink


def concatenated(**kw: Any) -> int:
    print(kw["o" "ld"])
    return sink(**kw)


def sets_new(**kw: Any) -> int:
    return sink(**{**kw, "new": 2})


def defaults_new(**kw: Any) -> int:
    kw.setdefault("new", 2)
    return sink(**kw)


def takes_new(*, new: int = 2, **kw: Any) -> int:
    return sink(**kw) + new


def chain_new(**kw: Any) -> int:
    return takes_new(**kw)


def passes_new(**kw: Any) -> int:
    return sink(new=2, **kw)


class Dynamic(factory()):
    def __init__(self, **kw: Any) -> None:
        self.total = sink(**kw)


def dynamic_one(**kw: Any) -> Dynamic:
    return Dynamic(**kw)


def dynamic_two(**kw: Any) -> Dynamic:
    return Dynamic(**kw)


def plain(**kw: Any) -> int:
    return sink(**kw)
"""
MEASURED = """\
from typing import Any

from pkg.s import sink


def len(mapping: dict[str, Any]) -> int:
    return mapping["o" + "ld"]


def measured(**kw: Any) -> int:
    return len(kw) + sink(**kw)
"""
UNPROVABLE_NAMES = ["c.concatenated", "c.sets_new", "c.defaults_new", "c.takes_new", "c.chain_new", "c.passes_new", "c.dynamic_one",
                    "c.dynamic_two", "m.measured"]
UNPROVABLE_USE = "from typing import Any\n\nfrom pkg import c, m\n\n\ndef use(registry: dict[str, Any]) -> None:\n" + "".join(
    f"    {name}(old=1)\n" for name in UNPROVABLE_NAMES) + '    registry["build"](**{"old": 1})\n    c.plain(old=1)\n'


def test_a_carrier_whose_flow_of_either_name_is_unprovable_lists_its_keyword(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    files = {"pkg/s.py": SINK, "pkg/c.py": UNPROVABLE, "pkg/m.py": MEASURED, "pkg/use.py": UNPROVABLE_USE}
    root = write_project(tmp_path / "p", files)
    argv = ["--apply", "rename", "--file", "pkg/s.py", "--symbol", "sink(old)", "--new-name", "new", "--allow-blindspots"]
    code, _out, err = run(root, argv, monkeypatch, capsys)
    assert code == 0
    callees = [*UNPROVABLE_NAMES, 'registry["build"]']
    assert err.splitlines() == [_unlinked("pkg/use.py", 7 + i, callee, "old") for i, callee in enumerate(callees)]
    assert read(root, "pkg/use.py") == UNPROVABLE_USE.replace("c.plain(old=1)", "c.plain(new=1)")
    assert (read(root, "pkg/c.py"), read(root, "pkg/m.py")) == (UNPROVABLE, MEASURED)


DECORATED_SINKS = Template("""\
import functools
from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager
from typing import Any


@contextmanager
def engine(*, $engine: int) -> Iterator[int]:
    yield $engine


@functools.lru_cache
def cached($cached: int) -> int:
    return $cached


class K:
    @staticmethod
    def make(*, $make: int) -> int:
        return $make


def mk_engine(**kw: Any) -> AbstractContextManager[int]:
    return engine(**kw)


def mk_cached(**kw: Any) -> int:
    return cached(**kw)


def mk_static(**kw: Any) -> int:
    return K.make(**kw)


def use() -> None:
    print(mk_engine($engine=1), mk_cached(models=1), mk_static($make=1))
""")
DECORATED_SLOTS = {"engine": "models", "cached": "models", "make": "models"}


@pytest.mark.parametrize(("symbol", "slot"), [("engine(models)", "engine"), ("K.make(models)", "make")])
def test_a_decorated_sink_whose_signature_follows_the_rename_carries_the_keyword(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], symbol: str, slot: str
) -> None:
    root = write_project(tmp_path / "p", {"pkg/q.py": DECORATED_SINKS.substitute(DECORATED_SLOTS)})
    code, _out, err = run(root, _rename(symbol, "datasets"), monkeypatch, capsys)
    assert (code, err) == (0, "")
    assert read(root, "pkg/q.py") == DECORATED_SINKS.substitute({**DECORATED_SLOTS, slot: "datasets"})


def test_a_decorated_sink_whose_signature_drops_the_parameter_lists_the_keyword(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = write_project(tmp_path / "p", {"pkg/q.py": DECORATED_SINKS.substitute(DECORATED_SLOTS)})
    code, _out, err = run(root, _rename("cached(models)", "datasets", "--allow-blindspots"), monkeypatch, capsys)
    assert (code, err.splitlines()) == (0, [_unlinked("pkg/q.py", 36, "mk_cached", "models")])
    assert read(root, "pkg/q.py") == DECORATED_SINKS.substitute({**DECORATED_SLOTS, "cached": "datasets"})


BOTH_RECEIVE = """\
from typing import Any


class Reads:
    def __new__(cls, **kw: Any) -> "Reads":
        print(kw["old"])
        return super().__new__(cls)

    def __init__(self, *, old: int) -> None:
        self.total = old


class Passes:
    def __new__(cls, **kw: Any) -> "Passes":
        return super().__new__(cls)

    def __init__(self, *, old: int) -> None:
        self.total = old


def reads(**kw: Any) -> Reads:
    return Reads(**kw)


def passes(**kw: Any) -> Passes:
    return Passes(**kw)


def use() -> None:
    print(reads(old=1), passes(old=1))
"""


def test_a_carrier_into_a_class_whose_other_constructor_reads_the_key_lists_its_keyword(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    entries = [{"file": "pkg/q.py", "symbol": f"{name}.__init__(old)", "new_name": "new"} for name in ("Reads", "Passes")]
    root = write_project(tmp_path / "p", {"pkg/q.py": BOTH_RECEIVE, "map.yaml": yaml.safe_dump(entries)})
    code, _out, err = run(root, ["--apply", "rename-map", "map.yaml", "--allow-blindspots"], monkeypatch, capsys)
    assert code == 0
    assert _unlinked("pkg/q.py", 30, "reads", "old") in err.splitlines()
    assert "print(reads(old=1), passes(new=1))" in read(root, "pkg/q.py")


UNPACKED_TWICE = """\
def f(*, old: int = 0, **rest: int) -> int:
    return old + len(rest)


def use() -> int:
    return f(**{"old": 1}, **{"new": 2})
"""


def test_a_key_meeting_the_new_name_in_another_unpacked_literal_is_a_name_conflict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = write_project(tmp_path / "p", {"pkg/q.py": UNPACKED_TWICE})
    before = file_tree(root)
    code, _out, err = run(root, _rename("f(old)", "new"), monkeypatch, capsys)
    assert code == 1
    conflict = message("refactor.name-conflict", name="new", path="pkg/q.py", line=6)
    assert err.splitlines()[-1] == entry_refusal("pkg/q.py f(old)", conflict)
    assert file_tree(root) == before


COLLISION = HELPER.replace('q(measures=["n"])', 'q(measures=["n"], metrics=[])')


def test_a_keyword_collision_through_a_carrier_is_a_name_conflict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = write_project(tmp_path / "p", {"pkg/q.py": COLLISION})
    before = file_tree(root)
    code, _out, err = run(root, _rename("Query.measures", "metrics"), monkeypatch, capsys)
    assert code == 1
    conflict = message("refactor.name-conflict", name="metrics", path="pkg/q.py", line=17)
    assert err.splitlines()[-1] == entry_refusal("pkg/q.py Query.measures", conflict)
    assert file_tree(root) == before


PARAMS = """\
from typing import Any


def kwonly(*, model_name: str) -> str:
    return model_name


def wrap(**kw: str) -> str:
    return kwonly(**kw)


def own(model_name: str = "", **kw: str) -> str:
    return model_name + kwonly(**kw)


def opaque(mapping: dict[str, str]) -> str:
    return kwonly(**mapping)


class Engine:
    def __init__(self, *, models: list[int]) -> None:
        self.size = len(models)

    def run(self, *, model_name: str) -> str:
        return model_name


def run_it(engine: Engine, **kw: str) -> str:
    return engine.run(**kw)


class Pool(Engine):
    def __init__(self, **kw: Any) -> None:
        super().__init__(**kw)


def make(**kw: Any) -> Engine:
    return Engine(**kw)


def calls() -> list[object]:
    return [
        wrap(model_name="x"),
        own(model_name="x"),
        opaque({"model_name": "x"}),
        kwonly(**{"model_name": "x"}),
        wrap(**{"model_name": "x"}),
        make(models=[1]),
        Pool(models=[1]),
        run_it(Pool(), model_name="x"),
    ]
"""


def test_parameter_renames_follow_carriers_into_functions_and_constructors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    entries = [{"file": "pkg/s.py", "symbol": "kwonly(model_name)", "new_name": "dataset_name"},
               {"file": "pkg/s.py", "symbol": "Engine.__init__(models)", "new_name": "datasets"},
               {"file": "pkg/s.py", "symbol": "Engine.run(model_name)", "new_name": "dataset_name"}]
    root = write_project(tmp_path / "p", {"pkg/s.py": PARAMS, "map.yaml": yaml.safe_dump(entries)})
    code, _out, err = run(root, ["--apply", "rename-map", "map.yaml"], monkeypatch, capsys)
    assert (code, err) == (0, "")
    expected = PARAMS
    for old, new in [("def kwonly(*, model_name: str) -> str:\n    return model_name",
                      "def kwonly(*, dataset_name: str) -> str:\n    return dataset_name"),
                     ("*, models: list[int]) -> None:\n        self.size = len(models)",
                      "*, datasets: list[int]) -> None:\n        self.size = len(datasets)"),
                     ('wrap(model_name="x")', 'wrap(dataset_name="x")'),
                     ('kwonly(**{"model_name": "x"})', 'kwonly(**{"dataset_name": "x"})'),
                     ('wrap(**{"model_name": "x"})', 'wrap(**{"dataset_name": "x"})'),
                     ("def run(self, *, model_name: str) -> str:\n        return model_name",
                      "def run(self, *, dataset_name: str) -> str:\n        return dataset_name"),
                     ('run_it(Pool(), model_name="x")', 'run_it(Pool(), dataset_name="x")'),
                     ("make(models=[1])", "make(datasets=[1])"), ("Pool(models=[1])", "Pool(datasets=[1])")]:
        assert expected.count(old) == 1
        expected = expected.replace(old, new)
    assert read(root, "pkg/s.py") == expected
