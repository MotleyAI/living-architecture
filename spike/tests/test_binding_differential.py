"""The Rust port's binding dump equals dr's, byte for byte, on every file each CPython version accepts."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from conftest import python_dumps, rust_dumps


def test_binding_dump(corpus_file: tuple[str, Path, str, str]) -> None:
    _, root, rel, version = corpus_file
    expected = python_dumps("binding_dump.py", version, root)[rel]
    if json.loads(expected)["status"] == "syntax-error":
        pytest.skip(f"CPython {version} rejects it")
    found, error = rust_dumps("binding-dump", version, root)
    assert rel in found, f"binding-dump gave no dump: {error[-2000:]}"
    assert found[rel] == expected
