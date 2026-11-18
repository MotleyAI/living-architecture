import functools
from collections.abc import AsyncIterator, Callable, Iterator
from contextlib import asynccontextmanager, contextmanager
from typing import ParamSpec, TypeVar

P = ParamSpec("P")
R = TypeVar("R")


def logged(fn: Callable[P, R]) -> Callable[P, R]:
    @functools.wraps(fn)
    def inner(*args: P.args, **kwargs: P.kwargs) -> R:
        return fn(*args, **kwargs)

    return inner


@asynccontextmanager
async def engine(*, models: list[int]) -> AsyncIterator[list[int]]:
    yield models


@contextmanager
def sync_engine(*, models: list[int]) -> Iterator[list[int]]:
    yield models


def plain(*, models: list[int]) -> list[int]:
    return models


@logged
def wrapped(*, models: list[int]) -> list[int]:
    return models


class C:
    @contextmanager
    def scope(self, *, models: list[int]) -> Iterator[list[int]]:
        yield models
