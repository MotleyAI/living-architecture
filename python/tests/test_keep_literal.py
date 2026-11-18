"""Python `--keep-literal KEY`: a dict display holding the key is kept whole from every rewrite."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from refactor_cli import git_project, leftover, read, rename_argv, run

from living_architecture.contract import message

MODELS = (
    "from pydantic import BaseModel\n\n\n"
    'class Member(BaseModel):\n    type: str = ""\n\n\n'
    "class Ds(BaseModel):\n    columns: list[Member] = []\n"
)
MODELS_AFTER = MODELS.replace("    columns:", "    fields:")
HEAD = "from pkg.m import Ds\n\n"
WARNING = "refactor.keep-literal-unneeded"


@pytest.fixture
def kept(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]):
    """Rename `Ds.columns -> fields --keep-literal version` (or `argv`) over `pkg/n.py`; returns the root and the run."""

    def go(use: str, *flags: str, argv: list[str] | None = None, files: dict[str, str] | None = None):
        root = git_project(tmp_path / "proj", {"pkg/m.py": MODELS, "pkg/n.py": use, **(files or {})})
        default = rename_argv("pkg/m.py", "Ds.columns", "fields", "--keep-literal", "version", *flags)
        return root, run(root, argv or default, monkeypatch, capsys)

    return go


def _validate(*literals: str) -> str:
    return HEAD + "".join(f"D{i} = Ds.model_validate({literal})\n" for i, literal in enumerate(literals))


def test_a_versioned_document_is_kept_and_a_plain_one_renamed(kept) -> None:
    use = _validate('{"version": 3, "columns": []}', '{"columns": []}')
    root, (code, _out, err) = kept(use)
    assert (code, err) == (0, "")
    assert read(root, "pkg/n.py") == _validate('{"version": 3, "columns": []}', '{"fields": []}')
    assert read(root, "pkg/m.py") == MODELS_AFTER


def test_a_literal_bound_to_a_name_is_kept(kept) -> None:
    use = HEAD + '\ndef load() -> Ds:\n    doc = {"version": 3, "columns": []}\n    return Ds.model_validate(doc)\n'
    root, (code, _out, err) = kept(use)
    assert (code, err) == (0, "")
    assert read(root, "pkg/n.py") == use


def test_single_quoted_and_prefixed_keys_match_by_their_source_text(kept) -> None:
    use = _validate("{'version': 3, \"columns\": []}", '{r"version": 3, "columns": []}', '{"\\x76ersion": 3, "columns": []}')
    root, (code, _out, _err) = kept(use)
    assert code == 0
    assert read(root, "pkg/n.py") == use.replace('{"\\x76ersion": 3, "columns": []}', '{"\\x76ersion": 3, "fields": []}')


@pytest.mark.parametrize(
    "literal",
    [
        '{"versions": 1, "columns": []}',
        '{"ver" "sion": 3, "columns": []}',
        '{**{"version": 3}, "columns": []}',
        '{f"version": 3, "columns": []}',
        '{VERSION: 3, "columns": []}',
        '{"columns": [], "meta": "version"}',
    ],
    ids=["other-key", "concatenated-key", "unpacking", "f-string-key", "name-key", "value"],
)
def test_other_forms_do_not_match(kept, literal: str) -> None:
    use = 'VERSION = "version"\n' + _validate(literal, '{"version": 1, "columns": []}')
    root, (code, _out, err) = kept(use)
    assert (code, err) == (0, "")
    assert read(root, "pkg/n.py") == 'VERSION = "version"\n' + _validate(
        literal.replace('"columns"', '"fields"'), '{"version": 1, "columns": []}'
    )


def test_literals_nested_in_a_kept_literal_are_kept_and_a_nested_match_keeps_only_itself(kept) -> None:
    entries = [{"file": "pkg/m.py", "symbol": "Ds.columns", "new_name": "fields"},
               {"file": "pkg/m.py", "symbol": "Member.type", "new_name": "kind"}]
    use = _validate(
        '{"version": 2, "columns": [{"type": "INT"}]}',
        '{"columns": [{"version": 1, "type": "INT"}, {"type": "TEXT"}]}',
    )
    argv = ["--apply", "rename-map", "map.yaml", "--keep-literal", "version"]
    root, (code, _out, err) = kept(use, argv=argv, files={"map.yaml": yaml.safe_dump(entries, sort_keys=False)})
    assert (code, err) == (0, "")
    assert read(root, "pkg/n.py") == _validate(
        '{"version": 2, "columns": [{"type": "INT"}]}',
        '{"fields": [{"version": 1, "type": "INT"}, {"kind": "TEXT"}]}',
    )


def test_an_edit_overlapping_a_kept_literal_is_dropped_whatever_made_it(kept) -> None:
    use = HEAD + '\ndef dump(d: Ds) -> dict[str, object]:\n    return {"version": 3, "count": len(d.columns)}\n'
    root, (code, _out, err) = kept(use)
    assert (code, err) == (0, "")
    assert read(root, "pkg/n.py") == use


def test_the_key_is_repeatable(kept) -> None:
    use = _validate('{"version": 3, "columns": []}', '{"schema": 1, "columns": []}', '{"columns": []}')
    root, (code, _out, err) = kept(use, "--keep-literal", "schema")
    assert (code, err) == (0, "")
    assert read(root, "pkg/n.py") == use.replace('({"columns"', '({"fields"')


def test_no_name_conflict_inside_a_kept_literal(kept) -> None:
    use = _validate('{"version": 3, "columns": [], "fields": []}', '{"columns": []}')
    root, (code, _out, err) = kept(use)
    assert (code, err) == (0, "")
    assert read(root, "pkg/n.py") == use.replace('({"columns"', '({"fields"')


def test_a_blind_spot_inside_a_kept_literal_does_not_block(kept) -> None:
    use = _validate('{"columns": []}') + '\n\ndef dump(x):\n    return {"version": 1, "count": x.columns}\n'
    root, (code, _out, err) = kept(use)
    assert (code, err) == (0, "")
    assert read(root, "pkg/n.py") == use.replace('({"columns"', '({"fields"')


def test_a_blind_spot_outside_a_kept_literal_still_blocks(kept) -> None:
    use = _validate('{"version": 1, "columns": []}') + '\n\ndef dump(x):\n    return {"count": x.columns}\n'
    root, (code, _out, err) = kept(use)
    assert code == 1
    assert message("compliance.attr-blindspot", path="pkg/n.py", line=7, receiver="x", attr="columns", type="Unknown") in err
    assert read(root, "pkg/m.py") == MODELS


BODIES = (
    "from typing import Any\n\n\n"
    "def post(json: dict[str, Any]) -> None: ...\n\n\n"
    'post(json={"version": 3, "columns": ["id"]})\n'
    'post(json={"columns": ["id"]})\n'
)


def test_a_listed_mention_inside_a_kept_literal_is_not_listed(kept) -> None:
    use = _validate('{"version": 1, "columns": []}')
    root, (code, _out, err) = kept(use, "--docs", files={"pkg/o.py": BODIES})
    assert code == 0
    assert err == f"{leftover('pkg/o.py', 8, 'string', 'columns')}\n"
    assert read(root, "pkg/o.py") == BODIES


def test_a_key_matching_nothing_touched_warns_and_the_rename_is_written(kept) -> None:
    use = _validate('{"columns": []}') + 'META = {"schema_version": 2}\n'
    argv = rename_argv("pkg/m.py", "Ds.columns", "fields", "--keep-literal", "schema_version")
    root, (code, _out, err) = kept(use, argv=argv)
    assert (code, err) == (0, f"{message(WARNING, key='schema_version')}\n")
    assert read(root, "pkg/n.py") == use.replace('({"columns"', '({"fields"')


def test_each_unneeded_key_warns_in_command_line_order(kept) -> None:
    use = _validate('{"version": 3, "columns": []}')
    _root, (code, _out, err) = kept(use, "--keep-literal", "b", "--keep-literal", "a")
    assert code == 0
    assert err.splitlines() == [message(WARNING, key="b"), message(WARNING, key="a")]


def test_a_field_name_string_in_a_kept_literal_is_kept(kept) -> None:
    use = HEAD + 'KEPT = {"version": 3, "info": Ds.model_fields["columns"]}\nPLAIN = {"info": Ds.model_fields["columns"]}\n'
    root, (code, _out, err) = kept(use)
    assert (code, err) == (0, "")
    assert read(root, "pkg/n.py") == use.replace('PLAIN = {"info": Ds.model_fields["columns"]', 'PLAIN = {"info": Ds.model_fields["fields"]')


def test_a_pick_beside_a_rewritten_source_literal_rewrites_the_mention_only(kept) -> None:
    use = HEAD + 'def show(ds: Ds) -> object:\n    name = "columns"  # the `columns` field\n    return getattr(ds, name), name\n'
    argv = rename_argv("pkg/m.py", "Ds.columns", "fields", "--docs", "--docs-pick", "pkg/n.py:4")
    root, (code, _out, err) = kept(use, argv=argv)
    assert code == 0
    assert read(root, "pkg/n.py") == use.replace("columns", "fields")
    assert [line.split(": ")[:2] for line in err.splitlines()] == [["pkg/n.py:5", "unverified-read"]]
