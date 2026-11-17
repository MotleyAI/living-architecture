"""The Python canonical binding dump, pinned by hand on two small files."""

from __future__ import annotations

import json

import pytest
from binding_dump import canonical, dump
from corpus import DATA

T, F, N = True, False, None


def decl(module: str, key: str) -> list[str]:
    return ["decl", module, key]


PIN_SCOPES = {
    "status": "ok",
    "scopes": [
        {"id": 0, "kind": "module", "parent": N,
         "raw": [["f", [decl("pin_scopes", "3:0")]], ["g", [decl("pin_scopes", "2:0")]], ["os", [["module", "os", ""]]]],
         "bindings": [["f", [decl("pin_scopes", "3:0")]], ["g", [decl("pin_scopes", "2:0"), decl("pin_scopes", "5:4")]],
                      ["os", [["module", "os", ""]]]],
         "globals": [], "nonlocals": []},
        {"id": 1, "kind": "function", "parent": 0,
         "raw": [["a", [N]], ["g", [decl("pin_scopes", "5:4")]]], "bindings": [["a", [N]]],
         "globals": ["g"], "nonlocals": []},
        {"id": 2, "kind": "comprehension", "parent": 1,
         "raw": [["b", [decl("pin_scopes", "6:18")]]], "bindings": [["b", [decl("pin_scopes", "6:18")]]],
         "globals": [], "nonlocals": []},
    ],
    "sites": [[0, "f", [20]], [0, "g", [10, 43]], [0, "os", [7]], [1, "a", [22]], [2, "b", [67]]],
    "points": [[0, "f", [[20, 77, N]]], [0, "g", [[10, 11, [14, 15]], [43, 44, [47, 48]]]], [0, "os", [[7, 9, N]]],
               [1, "a", [[22, 77, N]]], [2, "b", [[67, 68, N]]]],
    "occurrences": [["a", [[22, 1, T], [47, 1, F], [61, 2, F]]], ["b", [[67, 2, T]]], ["f", [[20, 0, T]]],
                    ["g", [[10, 0, T], [43, 1, T]]], ["os", [[7, 0, T], [72, 1, F]]]],
    "stars": [],
    "all_names": N,
    "loops": [],
    "resolution": [[0, "f", 0, 0], [0, "g", 0, 0], [0, "os", 0, 0], [1, "a", 1, 1], [1, "g", 0, 0], [1, "os", 1, 0],
                   [2, "a", 2, 1], [2, "b", 2, 2]],
    "may_precede": [],
    "joined": [[0, []], [1, []], [2, []]],
}

PIN_CLASS_LOOP = {
    "status": "ok",
    "scopes": [
        {"id": 0, "kind": "module", "parent": N,
         "raw": [["C", [decl("pin_class_loop", "2:0")]], ["n", [decl("pin_class_loop", "1:0")]]],
         "bindings": [["C", [decl("pin_class_loop", "2:0")]], ["n", [decl("pin_class_loop", "1:0")]]],
         "globals": [], "nonlocals": []},
        {"id": 1, "kind": "class", "parent": 0,
         "raw": [["i", [decl("pin_class_loop", "3:8")]], ["n", [decl("pin_class_loop", "5:8")]],
                 ["x", [decl("pin_class_loop", "4:8")]], ["y", [decl("pin_class_loop", "6:4")]]],
         "bindings": [["i", [decl("pin_class_loop", "3:8")]], ["n", [decl("pin_class_loop", "5:8")]],
                      ["x", [decl("pin_class_loop", "4:8")]], ["y", [decl("pin_class_loop", "6:4")]]],
         "globals": [], "nonlocals": []},
    ],
    "sites": [[0, "C", [12]], [0, "n", [0]], [1, "i", [23]], [1, "n", [61]], [1, "x", [42]], [1, "y", [71]]],
    "points": [[0, "C", [[12, 76, N]]], [0, "n", [[0, 1, [4, 5]]]], [1, "i", [[23, 24, [28, 32]]]],
               [1, "n", [[61, 62, [65, 66]]]], [1, "x", [[42, 43, [51, 52]]]], [1, "y", [[71, 72, [75, 76]]]]],
    "occurrences": [["C", [[12, 0, T], [46, 1, F]]], ["i", [[23, 1, T], [65, 1, F]]],
                    ["n", [[0, 0, T], [61, 1, T], [51, 1, F], [75, 1, F]]], ["x", [[42, 1, T]]], ["y", [[71, 1, T]]]],
    "stars": [],
    "all_names": N,
    "loops": [[1, [[[23, 24], [42, 66]]]]],
    "resolution": [[0, "C", 0, 0], [0, "n", 0, 0], [1, "C", 1, 0], [1, "i", 1, 1], [1, "n", 1, 1], [1, "x", 1, 1],
                   [1, "y", 1, 1]],
    "may_precede": [[1, "i", 23, T], [1, "i", 65, T], [1, "n", 0, F], [1, "n", 51, T], [1, "n", 61, T], [1, "n", 75, T],
                    [1, "x", 42, T], [1, "y", 71, F]],
    "joined": [[0, []], [1, []]],
}


@pytest.mark.parametrize(("rel", "expected"), [("pin_scopes.py", PIN_SCOPES), ("pin_class_loop.py", PIN_CLASS_LOOP)])
def test_pinned_dump(rel: str, expected: dict[str, object]) -> None:
    assert dump(DATA, rel) == expected


@pytest.mark.parametrize(("rel", "status"), [("syntax_error.py", "syntax-error"), ("invalid_cookie.py", "undecodable"),
                                              ("cookie_mismatch_undecodable.py", "undecodable")])
def test_status_only_dump(rel: str, status: str) -> None:
    assert dump(DATA, rel) == {"status": status}


def test_canonical_text_sorts_keys_and_keeps_non_ascii() -> None:
    assert canonical({"b": ["é", None], "a": True}) == '{"a":true,"b":["é",null]}'


def test_dump_is_json_round_trip_stable() -> None:
    text = canonical(dump(DATA, "binding_forms.py"))
    assert canonical(json.loads(text)) == text
