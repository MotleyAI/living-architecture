"""Destination."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pkg.y import U


def h(u: U) -> None:
    print(u)
