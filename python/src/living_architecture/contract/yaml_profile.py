"""The shared YAML profile: YAML 1.1 as PyYAML's safe loader reads it, within a closed tag set, refusing a repeated key."""

from __future__ import annotations

import datetime as dt
import math
import re
from typing import Any

import yaml
from typing_extensions import override

YAMLError = yaml.YAMLError

# What PyYAML's safe constructors raise, unwrapped, for a scalar they cannot construct (`2024-13-01`, `!!int x`).
_CONSTRUCT_ERRORS = (ValueError, KeyError, IndexError, AttributeError, TypeError, OverflowError)

_MERGE_TAG = "tag:yaml.org,2002:merge"

# Key identities the profile's comparator treats specially; every other key compares under Python equality, which
# is already exact across bool, int and float.
_MERGE_KEY = object()
_NAN_KEY = object()


class DuplicateKeyError(YAMLError):
    """A mapping repeats a key: the first occurrence's normalized key and the 1-based lines of both."""

    def __init__(self, key: object, first: int, second: int) -> None:
        from living_architecture.contract.render import message  # ALLOW(import-not-top): an import cycle

        super().__init__(message("yaml.duplicate-key", key=key, first=first, second=second))
        self.key = key
        self.first = first
        self.second = second


class _ProfileLoader(yaml.SafeLoader):
    """The safe loader without the tags outside the profile's closed set, recording where each mapping key starts."""

    def __init__(self, stream: str) -> None:
        super().__init__(stream)
        self.key_marks: dict[yaml.Node, list[yaml.Mark]] = {}

    @override
    def compose_node(self, parent: yaml.Node | None, index: int) -> yaml.Node | None:
        # A mapping composes each key with no index; an alias key's node is its anchor's, so its mark is taken here.
        if isinstance(parent, yaml.MappingNode) and index is None:
            self.key_marks.setdefault(parent, []).append(self.peek_event().start_mark)
        return super().compose_node(parent, index)


for _name in ("binary", "set", "omap", "pairs"):
    _ProfileLoader.add_constructor(f"tag:yaml.org,2002:{_name}", _ProfileLoader.construct_undefined)


def _key(loader: _ProfileLoader, node: yaml.ScalarNode) -> tuple[object, object]:
    """A scalar key's normalized value and its identity under the profile's key comparator."""
    if node.tag == _MERGE_TAG:
        return "<<", _MERGE_KEY
    value = loader.construct_object(node)
    if isinstance(value, dt.date):
        value = value.isoformat()
    if isinstance(value, float) and math.isnan(value):
        return value, _NAN_KEY
    return value, value


def _check_keys(loader: _ProfileLoader, node: yaml.Node, seen: set[yaml.Node]) -> None:
    """Raise DuplicateKeyError for the first repeated mapping key below `node` in document order."""
    if node in seen:
        return
    seen.add(node)
    if isinstance(node, yaml.SequenceNode):
        for item in node.value:
            _check_keys(loader, item, seen)
    elif isinstance(node, yaml.MappingNode):
        firsts: dict[object, tuple[object, int]] = {}
        for (key_node, value_node), mark in zip(node.value, loader.key_marks.get(node, [])):
            if isinstance(key_node, yaml.ScalarNode):
                key, identity = _key(loader, key_node)
                if identity in firsts:
                    first_key, first_line = firsts[identity]
                    raise DuplicateKeyError(first_key, first_line, mark.line + 1)
                firsts[identity] = (key, mark.line + 1)
            _check_keys(loader, key_node, seen)
            _check_keys(loader, value_node, seen)


# Line breaks to YAML 1.1 that the npm twin's YAML 1.2 library reads as content.
_UNICODE_BREAKS = re.compile("[\x85\u2028\u2029]")


def load_yaml(text: str) -> Any:
    if (found := _UNICODE_BREAKS.search(text)) is not None:
        raise YAMLError(f"a raw U+{ord(found.group()):04X} line break at offset {found.start()}")
    loader = _ProfileLoader(text)
    try:
        node = loader.get_single_node()
        if node is None:
            return None
        try:
            _check_keys(loader, node, set())
        except DuplicateKeyError:
            # A document that cannot be constructed reports that before a repeat; construction flattens merges, so it
            # runs after the check.
            loader.construct_document(node)
            raise
        return loader.construct_document(node)
    except _CONSTRUCT_ERRORS as exc:
        raise YAMLError(f"cannot construct a scalar: {exc}") from exc
    finally:
        loader.dispose()
