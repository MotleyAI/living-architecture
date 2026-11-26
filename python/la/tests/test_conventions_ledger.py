"""The stealth waiver ledger: loading against the shared schema and matching violations by path, rule and line text."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from living_architecture.conventions.ledger import LedgerEntry, load_ledger, waived
from trmv.config import ConfigError

ENTRY = LedgerEntry(path="src/a.py", rule="import-not-top", line="import os", reason="optional dependency")


def _ledger(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "waivers.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def test_loads_every_entry(tmp_path: Path) -> None:
    path = _ledger(tmp_path, "- {path: src/a.py, rule: import-not-top, line: import os, reason: optional dependency}\n")
    assert load_ledger(path) == [ENTRY]


def test_a_missing_ledger_holds_no_entries(tmp_path: Path) -> None:
    assert load_ledger(tmp_path / "waivers.yaml") == []


@pytest.mark.parametrize("text", [
    "- {path: src/a.py, rule: import-not-top, line: import os}\n",
    "- {path: src/a.py, rule: import-not-top, line: import os, reason: x, extra: y}\n",
    "- {path: src/a.py, rule: import-not-top, line: 3, reason: x}\n",
    "{path: src/a.py}\n",
    "- [\n",
])
def test_a_malformed_ledger_names_the_file(tmp_path: Path, text: str) -> None:
    path = _ledger(tmp_path, text)
    with pytest.raises(ConfigError, match=re.escape(str(path))):
        load_ledger(path)


@pytest.mark.parametrize("rule", ["text-ratio", "no-such-rule"])
def test_a_rule_must_be_waivable(tmp_path: Path, rule: str) -> None:
    path = _ledger(tmp_path, f"- {{path: src/a.py, rule: {rule}, line: import os, reason: x}}\n")
    with pytest.raises(ConfigError, match=re.escape(str(path))):
        load_ledger(path)


@pytest.mark.parametrize("line", ["import os", "        import os", "import os\r", "\timport os  \r"])
def test_the_line_is_matched_trimmed_without_its_carriage_return(line: str) -> None:
    assert waived([ENTRY], path="src/a.py", rule="import-not-top", line=line)


@pytest.mark.parametrize(("path", "rule", "line"), [
    ("src/b.py", "import-not-top", "import os"),
    ("src/a.py", "composite-assert", "import os"),
    ("src/a.py", "import-not-top", "import sys"),
    ("./src/a.py", "import-not-top", "import os"),
])
def test_path_rule_and_line_must_all_match(path: str, rule: str, line: str) -> None:
    assert not waived([ENTRY], path=path, rule=rule, line=line)


def test_one_entry_waives_every_matching_violation() -> None:
    hits = [waived([ENTRY], path="src/a.py", rule="import-not-top", line=text) for text in ("import os", "    import os")]
    assert hits == [True, True]
