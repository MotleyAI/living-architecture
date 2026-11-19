"""Doc."""

from __future__ import annotations

from typing import TYPE_CHECKING

try:
    import tomllib
except ImportError:
    import tomli as tomllib

if TYPE_CHECKING:
    from collections.abc import Iterator

X = 1
