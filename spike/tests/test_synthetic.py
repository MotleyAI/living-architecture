"""The synthetic inputs decode and parse, or not, as each was written to, under every CPython version."""

from __future__ import annotations

import json

import pytest
from conftest import VERSIONS, python_dumps
from corpus import DATA, py_files

OK, SYNTAX, UNDECODABLE = "ok", "syntax-error", "undecodable"


def since(version: str) -> dict[str, str]:
    return {v: OK if v >= version else SYNTAX for v in VERSIONS}


def every(status: str) -> dict[str, str]:
    return dict.fromkeys(VERSIONS, status)


EXPECTED: dict[str, dict[str, str]] = {
    "binding_forms.py": every(OK),
    "bom.py": every(OK),
    "bom_cookie_latin1.py": every(OK),
    "bom_cookie_utf8.py": every(OK),
    "cookie_dr_differs.py": every(UNDECODABLE),
    "cookie_mismatch_mojibake.py": every(OK),
    "cookie_mismatch_undecodable.py": every(UNDECODABLE),
    "cookie_second_line.py": every(OK),
    "crlf.py": every(OK),
    "form_feed.py": every(OK),
    "forward_refs.py": every(OK),
    "fstrings.py": every(OK),
    "fstrings_pep701.py": since("3.12"),
    "invalid_cookie.py": every(UNDECODABLE),
    "latin1_cookie.py": every(OK),
    "lone_cr.py": every(OK),
    "match_stmt.py": every(OK),
    "non_ascii_identifiers.py": every(OK),
    "pep695.py": since("3.12"),
    "pep696_defaults.py": since("3.13"),
    "pin_class_loop.py": every(OK),
    "pin_scopes.py": every(OK),
    "py314_only.py": since("3.14"),
    "syntax_error.py": every(SYNTAX),
    "walrus_comprehension.py": every(OK),
}


def test_every_synthetic_file_has_an_expectation() -> None:
    assert sorted(EXPECTED) == py_files(DATA)


@pytest.mark.parametrize("version", VERSIONS)
@pytest.mark.parametrize("rel", sorted(EXPECTED))
def test_status(rel: str, version: str) -> None:
    assert json.loads(python_dumps("binding_dump.py", version, DATA)[rel])["status"] == EXPECTED[rel][version]
