"""A rename map's file: its entries, validated against the shared schema, and their one language."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict

from living_architecture.contract import (
    YAMLError,
    language_ids,
    language_of,
    load_yaml,
    message,
    schema,
    validate,
)
from living_architecture.refactor.locators import Locator


class MapError(Exception):
    """The map is invalid, mixes languages or holds duplicate entries; the message is user-facing (exit 2)."""


class MapEntry(BaseModel):
    """One entry: its 1-based index, its file (as given and as a path), its locator and its intent; a module entry's
    file is the module it renames."""

    model_config = ConfigDict(frozen=True)

    index: int
    file: str
    path: str
    locator: Locator = Locator()
    new_name: str | None = None
    retarget: str | None = None
    module: bool = False


def locator_text(root: Path, entry: MapEntry) -> str:
    """The entry's locator as a refusal prints it: its file relative to the project at `root`, then `:LINE[:COL]`,
    its symbol path or `offset N`; a module entry's is its file."""
    resolved = Path(entry.path).resolve()
    file = resolved.relative_to(root).as_posix() if resolved.is_relative_to(root) else entry.file
    locator = entry.locator
    if locator.offset is not None:
        return f"{file} offset {locator.offset}"
    if locator.line is not None:
        return f"{file}:{locator.line}" + (f":{locator.col}" if locator.col is not None else "")
    return f"{file} {locator.symbol}" if locator.symbol is not None else file


def load_map(raw: str, project: str) -> list[MapEntry]:
    """MAP's entries, files relative to `project`; `MapError` naming every invalid entry in index order."""

    def invalid(*indexes: int) -> MapError:
        return MapError("\n".join(message("refactor.map-invalid", map=raw, index=index) for index in indexes))

    try:
        document = load_yaml(Path(raw).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, YAMLError):
        raise invalid(1) from None
    if not isinstance(document, list) or not document:
        raise invalid(1)
    bad = [index for index, item in enumerate(document, 1) if validate(schema("rename-map"), [item])]
    if bad:
        raise invalid(*bad)
    entries: list[MapEntry] = []
    for index, item in enumerate(document, 1):
        if "module" in item:
            module = item["module"]
            entries.append(MapEntry(index=index, file=module, path=str(Path(project) / module), new_name=item["new_name"],
                                    module=True))
            continue
        locator = Locator(symbol=item.get("symbol"), line=item.get("line"), col=item.get("col"), offset=item.get("offset"))
        entries.append(MapEntry(
            index=index, file=item["file"], path=str(Path(project) / item["file"]), locator=locator,
            new_name=item.get("new_name"), retarget=item.get("retarget"),
        ))
    return entries


def map_language(raw: str, entries: list[MapEntry]) -> str | None:
    """The entries' one language (None for an unregistered extension); `MapError` when they hold more than one."""
    found = {language_of(e.path) for e in entries}
    if None in found:
        return None
    if len(found) > 1:
        ordered = [lang_id for lang_id in language_ids() if lang_id in found]
        raise MapError(message("refactor.map-mixed-languages", map=raw, languages=", ".join(ordered)))
    return found.pop()
