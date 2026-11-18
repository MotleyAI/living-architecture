import functools


@functools.lru_cache
def cached(datasets: int) -> int:
    return datasets


def plain(*, models: int) -> int:
    return models


def use() -> int:
    return cached(models=1) + plain(models=1)
