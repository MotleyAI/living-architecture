"""Positions mapped through text edits, for the type-check baseline's ranges."""

from __future__ import annotations

from collections.abc import Sequence

Edit = tuple[int, int, int]
"""A replaced span and the length of its new text."""


def map_range(edits: Sequence[Edit], start: int, end: int) -> tuple[int, int]:
    """`start:end` after `edits` (sorted, disjoint): a start inside a replaced span maps to the replacement's
    start, an end inside one to its end; an empty range maps both ends as its start."""
    new_start, new_end, shift = start, end, 0
    for s, e, length in edits:
        if s <= start < e:
            new_start = s + shift
        elif start >= e:
            new_start = start + shift + length - (e - s)
        if s < end <= e:
            new_end = s + shift + length
        elif end > e:
            new_end = end + shift + length - (e - s)
        shift += length - (e - s)
    return (new_start, new_start) if start == end else (new_start, new_end)
