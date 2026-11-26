def keys(chain: list[tuple[str, str]]) -> list[str]:
    return [m + "." + measure for m, measure in chain]


def other(model: str) -> str:
    return model
