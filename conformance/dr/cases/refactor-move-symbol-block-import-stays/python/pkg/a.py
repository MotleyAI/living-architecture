from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .x import T

try:
    import json
except ImportError:
    json = None


def f(t: T) -> str:
    return str(t)


def g() -> object:
    return json
