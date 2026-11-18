"""A word table: the words of a vocabulary rename, the carve-outs where a word keeps its old sense, and hand-written
map entries; a name's held words and its new name."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from living_architecture.contract import YAMLError, load_yaml, message, schema, validate
from living_architecture.refactor.compound import word_spans
from living_architecture.refactor.map_file import MapError

MATCHERS = ("annotated", "paths", "symbols")


def held_words(name: str, words: dict[str, str]) -> list[str]:
    """The `from`s `name` holds as whole words, without case, in the order it first spells them."""
    found = (name[start:end].lower() for start, end in word_spans(name))
    return list(dict.fromkeys(word for word in found if word in words))


def _cased(word: str, new: str) -> str:
    """`new` in `word`'s case form: capitals, capitalized or lowercase."""
    if len(word) > 1 and not any(ch.islower() for ch in word):
        return new.upper()
    return new.capitalize() if word[:1].isupper() else new


def replace_words(name: str, words: dict[str, str], keep: frozenset[str] = frozenset()) -> str:
    """`name` with each held word outside `keep` replaced once by its `to`, in the word's case form."""
    out: list[str] = []
    done = 0
    for start, end in word_spans(name):
        word = name[start:end]
        new = words.get(word.lower())
        if new is not None and word.lower() not in keep:
            out += [name[done:start], _cased(word, new)]
            done = end
    return "".join(out) + name[done:]


class CarveOut(BaseModel):
    """Where `words` keep their old sense: its matcher's key and listed values (`symbols`: `{file, symbol}`)."""

    model_config = ConfigDict(frozen=True)

    words: frozenset[str]
    matcher: str
    values: tuple[Any, ...]


class WordTable(BaseModel):
    """A valid table as named on the command line: `from` to `to`, the carve-outs in table order and the entries."""

    model_config = ConfigDict(frozen=True)

    raw: str
    words: dict[str, str]
    carve_outs: tuple[CarveOut, ...] = ()
    entries: tuple[dict[str, Any], ...] = ()


def _items(document: dict[str, Any], section: str) -> list[Any] | None:
    """A section's items; None when it is not a list."""
    found = document.get(section, [])
    return found if isinstance(found, list) else None


def _invalid_words(rows: list[Any]) -> list[int]:
    """The 1-based indexes of the rows the schema refuses, giving a `from` again or equal to its `to`."""
    bad: list[int] = []
    seen: set[str] = set()
    for index, row in enumerate(rows, 1):
        if validate(schema("word-table"), {"words": [row]}) or row["from"] in seen or row["from"] == row["to"]:
            bad.append(index)
        else:
            seen.add(row["from"])
    return bad


def _invalid_carve_outs(items: list[Any], froms: set[str]) -> list[int]:
    row = {"from": "a", "to": "b"}
    return [index for index, item in enumerate(items, 1)
            if validate(schema("word-table"), {"words": [row], "carve_outs": [item]}) or not set(item["words"]) <= froms]


def load_table(raw: str) -> WordTable:
    """TABLE (relative to the working directory); `MapError` with one `refactor.words-invalid` line per invalid item,
    in section and index order, `words` item 1 for a table that cannot be read as one."""

    def invalid(*items: tuple[str, int]) -> MapError:
        return MapError("\n".join(message("refactor.words-invalid", table=raw, section=s, index=i) for s, i in items))

    try:
        document = load_yaml(Path(raw).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, YAMLError):
        raise invalid(("words", 1)) from None
    rows = document.get("words") if isinstance(document, dict) else None
    if not isinstance(rows, list) or not rows:
        raise invalid(("words", 1))
    carves, entries = _items(document, "carve_outs"), _items(document, "entries")
    bad = [("words", i) for i in _invalid_words(rows)]
    froms = {row["from"] for i, row in enumerate(rows, 1) if ("words", i) not in bad}
    bad += [("carve_outs", 1)] if carves is None else [("carve_outs", i) for i in _invalid_carve_outs(carves, froms)]
    bad += [("entries", 1)] if entries is None else [
        ("entries", i) for i, item in enumerate(entries, 1) if validate(schema("rename-map"), [item])]
    if not bad and validate(schema("word-table"), document):
        bad = [("words", 1)]
    if bad:
        raise invalid(*bad)
    assert carves is not None and entries is not None
    carve_outs = tuple(
        CarveOut(words=frozenset(item["words"]), matcher=key, values=tuple(item[key]))
        for item in carves for key in MATCHERS if key in item
    )
    return WordTable(raw=raw, words={row["from"]: row["to"] for row in rows}, carve_outs=carve_outs, entries=tuple(entries))
