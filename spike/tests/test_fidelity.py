"""The fidelity harness: CPython's span and token dump, the comparer, and the ruff-side dump's shape."""

from __future__ import annotations

import copy
import json
import subprocess
from pathlib import Path

import pytest
from conftest import TARGET, VERSIONS, python_dumps, rust_build, rust_dumps
from corpus import DATA, py_files
from fidelity_compare import compare, main, tally
from fidelity_dump import dump, dump_text, encodings

Json = dict[str, object]


def parts(source: str) -> list[tuple[str, str]]:
    return [(e["kind"], source[e["chars"][0] : e["chars"][1]]) for e in dump_text(source)["strings"]]  # type: ignore[index,union-attr]


def test_string_prefixes() -> None:
    source = 'x = rb"a" + Rb\'b\' + BR"c" + u"d" + fR"{y}\\d"\n'
    assert parts(source) == [("str", 'rb"a"'), ("str", "Rb'b'"), ("str", 'BR"c"'), ("str", 'u"d"'),
                             ("fstr", 'fR"{y}\\d"'), ("fstr-field", "{y}"), ("fstr-literal", "\\d")]


def test_backslash_before_quote_in_raw_fstring() -> None:
    assert parts('x = rf"[\\"]{y}\\{z}"\n') == [("fstr", 'rf"[\\"]{y}\\{z}"'), ("fstr-literal", '[\\"]'), ("fstr-field", "{y}"),
                                                ("fstr-literal", "\\"), ("fstr-field", "{z}")]


def test_doubled_braces_stay_in_literal_runs() -> None:
    assert parts('f"{{a}} {b} }}"\n') == [("fstr", 'f"{{a}} {b} }}"'), ("fstr-literal", "{{a}} "), ("fstr-field", "{b}"),
                                          ("fstr-literal", " }}")]


def test_nested_format_spec() -> None:
    assert parts('f"{v:{w}.{p}f}"\n') == [("fstr", 'f"{v:{w}.{p}f}"'), ("fstr-field", "{v:{w}.{p}f}"),
                                          ("fstr-field", "{w}"), ("fstr-spec", "{w}.{p}f"), ("fstr-literal", "."),
                                          ("fstr-field", "{p}"), ("fstr-literal", "f")]


def test_conversion_debug_and_named_escape() -> None:
    assert parts('f"{x!r:>4}{x=}\\N{BULLET} {x}"\n') == [
        ("fstr", 'f"{x!r:>4}{x=}\\N{BULLET} {x}"'), ("fstr-field", "{x!r:>4}"), ("fstr-literal", ">4"),
        ("fstr-spec", ">4"), ("fstr-field", "{x=}"), ("fstr-literal", "\\N{BULLET} "), ("fstr-field", "{x}")]


def test_concatenated_parts_map_onto_one_node() -> None:
    source = 'z = "a" f"{b}" \'c\'\n'
    found = dump_text(source)["strings"]
    assert [(e["kind"], source[e["chars"][0] : e["chars"][1]]) for e in found] == [  # type: ignore[index,union-attr]
        ("str", '"a"'), ("fstr", 'f"{b}"'), ("fstr-field", "{b}"), ("str", "'c'")]
    assert {tuple(e["node"]) for e in found} == {(4, 18)}  # type: ignore[union-attr,arg-type]


def test_nested_fstring_maps_onto_its_own_node() -> None:
    source = "f\"{f'{x}'}\"\n"
    found = {source[e["chars"][0] : e["chars"][1]]: e["node"] for e in dump_text(source)["strings"]}  # type: ignore[index,union-attr]
    assert found == {"f\"{f'{x}'}\"": [0, 11], "{f'{x}'}": [0, 11], "f'{x}'": [3, 9], "{x}": [3, 9]}


def test_tokens_take_an_fstring_as_one_and_keep_comments() -> None:
    source = 'x = f"{y}"  # note\n'
    assert dump_text(source)["tokens"] == [{"kind": "fstring", "chars": [4, 10], "bytes": [4, 10]},
                                           {"kind": "comment", "chars": [12, 18], "bytes": [12, 18]}]


def test_nodes_leave_out_strings_and_fields_but_keep_field_expressions() -> None:
    nodes = dump_text('f"{y}"\n')["nodes"]
    assert nodes == [{"kind": "Expr", "chars": [0, 6], "bytes": [0, 6]}, {"kind": "Name", "chars": [3, 4], "bytes": [3, 4]}]


def test_character_and_byte_offsets_differ_after_non_ascii() -> None:
    found = dump_text('é = "ü"\n')
    assert {"kind": "Name", "chars": [0, 1], "bytes": [0, 2]} in found["nodes"]  # type: ignore[operator]
    assert found["tokens"] == [{"kind": "string", "chars": [4, 7], "bytes": [5, 9]}]


def test_undecodable_and_syntax_error() -> None:
    assert dump(DATA, "invalid_cookie.py") == {"status": "undecodable"}
    assert dump(DATA, "syntax_error.py") == {"status": "syntax-error", "tokens": "TokenError"}


def test_dr_rule_and_detect_encoding_disagree_only_where_written_to() -> None:
    found = {rel: encodings((DATA / rel).read_bytes()) for rel in py_files(DATA)}
    assert {rel: e for rel, e in found.items() if e["differ"]} == {
        "bom_cookie_latin1.py": {"dr": "iso8859-1", "cpython": "error", "differ": True},
        "cookie_dr_differs.py": {"dr": "utf-8: undecodable", "cpython": "iso8859-1", "differ": True},
        "cookie_second_line.py": {"dr": "iso8859-1", "cpython": "utf-8: undecodable", "differ": True},
    }


def _ok_dumps() -> list[Json]:
    return [d for d in (dump(DATA, rel) for rel in py_files(DATA)) if d["status"] == "ok"]


def test_equal_dumps_have_no_differences() -> None:
    assert all(compare(d, copy.deepcopy(d)) == [] for d in _ok_dumps())


def _planted(change: str) -> tuple[Json, Json, Json]:
    python = dump(DATA, "binding_forms.py")
    rust = copy.deepcopy(python)
    entry = next(e for e in rust["nodes"] if e["kind"] == "Name")  # type: ignore[union-attr,index]
    original = copy.deepcopy(entry)
    if change == "end":
        entry["chars"][1] += 1
        entry["bytes"][1] += 1
    elif change == "start":
        entry["chars"][0] -= 1
        entry["bytes"][0] -= 1
    elif change == "bytes":
        entry["bytes"][1] += 1
    else:
        rust["nodes"].remove(entry)  # type: ignore[union-attr]
    return python, rust, original


@pytest.mark.parametrize("change", ["end", "start", "bytes"])
def test_planted_offset_difference_is_reported(change: str) -> None:
    python, rust, original = _planted(change)
    diffs = compare(python, rust)
    assert [(d["section"], d["kind"], d["class"]) for d in diffs] == [("nodes", "Name", change)]
    assert diffs[0]["python"] == original


def test_missing_node_is_python_only() -> None:
    python, rust, original = _planted("missing")
    assert compare(python, rust) == [{"section": "nodes", "kind": "Name", "class": "python-only", "python": original,
                                      "rust": None}]


def test_status_difference() -> None:
    assert compare({"status": "ok", "tokens": []}, {"status": "syntax-error", "tokens": []}) == [
        {"section": "status", "kind": None, "class": "ok vs syntax-error", "python": "ok", "rust": "syntax-error"}]


def test_tally_counts_a_class_once_per_occurrence_with_the_first_example() -> None:
    python, rust, original = _planted("end")
    diffs = compare(python, rust)
    rows = tally({"b.py": diffs, "a.py": diffs})
    assert len(rows) == 1
    assert rows[0]["count"] == 2
    assert rows[0]["example"]["path"] == "a.py"  # type: ignore[index]
    assert rows[0]["example"]["python"] == original  # type: ignore[index]


def test_repeated_nodes_pair_with_the_nearest() -> None:
    def name(start: int, end: int) -> Json:
        return {"kind": "Name", "chars": [start, end], "bytes": [start, end]}

    python = {"status": "ok", "nodes": [name(0, 5), name(0, 9)]}
    rust = {"status": "ok", "nodes": [name(0, 10), name(0, 6)]}
    assert [(d["class"], d["python"], d["rust"]) for d in compare(python, rust)] == [
        ("end", name(0, 5), name(0, 6)), ("end", name(0, 9), name(0, 10))]


def test_compare_cli(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    python, rust, _ = _planted("end")
    (tmp_path / "py").write_text(f"b.py\t{json.dumps(python)}\n", encoding="utf-8")
    (tmp_path / "rs").write_text(f"b.py\t{json.dumps(rust)}\n", encoding="utf-8")
    assert main([str(tmp_path / "py"), str(tmp_path / "rs")]) == 0
    assert [(r["class"], r["count"]) for r in json.loads(capsys.readouterr().out)] == [("end", 1)]


def test_compare_cli_reports_files_one_side_left_out(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    doc = json.dumps({"status": "ok", "tokens": [], "nodes": [], "strings": []})
    (tmp_path / "py").write_text(f"a.py\t{doc}\nb.py\t{doc}\n", encoding="utf-8")
    (tmp_path / "rs").write_text(f"b.py\t{doc}\nc.py\t{doc}\n", encoding="utf-8")
    assert main([str(tmp_path / "py"), str(tmp_path / "rs")]) == 0
    rows = json.loads(capsys.readouterr().out)
    assert [(r["class"], r["count"], r["example"]["path"]) for r in rows] == [("missing-rust", 1, "a.py"),
                                                                              ("rust-only-file", 1, "c.py")]


@pytest.mark.parametrize("version", VERSIONS)
def test_cpython_dump_runs_on_every_version(version: str) -> None:
    found = python_dumps("fidelity_dump.py", version, DATA)
    statuses = python_dumps("binding_dump.py", version, DATA)
    assert sorted(found) == py_files(DATA)
    assert {rel: json.loads(t)["status"] for rel, t in found.items()} == {rel: json.loads(t)["status"] for rel, t in statuses.items()}


@pytest.mark.parametrize("section", ["tokens", "nodes", "strings"])
def test_cpython_versions_agree_on_the_synthetic_set(section: str) -> None:
    dumps = {v: {rel: json.loads(t) for rel, t in python_dumps("fidelity_dump.py", v, DATA).items()} for v in VERSIONS}
    for rel in py_files(DATA):
        seen = {json.dumps(dumps[v][rel][section]) for v in VERSIONS if dumps[v][rel]["status"] == "ok"}
        assert len(seen) <= 1, rel


def _span(value: object) -> bool:
    return isinstance(value, list) and len(value) == 2 and all(isinstance(v, int) for v in value) and value[0] <= value[1]


def _schema_errors(doc: Json) -> list[str]:
    """Where a dump departs from the schema `fidelity_dump` writes; its spans and classes are the measurement."""
    if doc.get("status") not in ("ok", "syntax-error", "undecodable"):
        return [f"status {doc.get('status')!r}"]
    errors: list[str] = []
    for section in ("tokens", "nodes", "strings") if doc["status"] == "ok" else ():
        entries = doc.get(section)
        if section == "tokens" and isinstance(entries, str):
            continue
        if not isinstance(entries, list):
            errors.append(f"{section} is not a list")
            continue
        keys = {"kind", "chars", "bytes", "node"} if section == "strings" else {"kind", "chars", "bytes"}
        for entry in entries:
            if set(entry) != keys or not isinstance(entry["kind"], str) or not (_span(entry["chars"]) and _span(entry["bytes"])):
                errors.append(f"{section} entry {entry}")
            elif section == "strings" and entry["node"] is not None and not _span(entry["node"]):
                errors.append(f"{section} node {entry}")
    return errors


@pytest.mark.parametrize("version", VERSIONS)
def test_ruff_dump_follows_the_cpython_schema(version: str) -> None:
    found, error = rust_dumps("fidelity-dump", version, DATA)
    assert sorted(found) == py_files(DATA), f"fidelity-dump gave no dumps: {error[-2000:]}"
    assert {rel: e for rel, text in found.items() if (e := _schema_errors(json.loads(text)))} == {}


def test_schema_check_accepts_cpython_dumps_and_catches_a_broken_entry() -> None:
    dumps = [dump(DATA, rel) for rel in py_files(DATA)]
    assert [e for d in dumps if (e := _schema_errors(d))] == []
    broken = copy.deepcopy(dump(DATA, "fstrings.py"))
    del broken["strings"][0]["node"]  # type: ignore[index]
    assert _schema_errors(broken)


@pytest.mark.parametrize("version", VERSIONS)
def test_ruff_parse_options_are_recorded(version: str) -> None:
    assert rust_build() is None
    done = subprocess.run([str(TARGET / "fidelity-dump"), "--describe-options", "--python-version", version],
                          capture_output=True, text=True, check=False)
    assert done.returncode == 0, done.stderr
    assert version in done.stdout
