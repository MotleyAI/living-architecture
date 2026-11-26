from collections.abc import Callable

from pkg.q import Query


def test_totals(make_query) -> None:
    make_query(measures=["n"])


def test_typed(make_query: Callable[..., Query]) -> None:
    make_query(measures=["n"])
