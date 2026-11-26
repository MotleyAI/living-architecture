from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .x import T


def f(t: T) -> str:
    return str(t)
