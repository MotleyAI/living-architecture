async def scopes(s: str) -> tuple[int, dict[str, int]]:
    return 0, {s: 1}


async def g(s: str) -> dict[str, int]:
    _scopes, ds_by_model = await scopes(s)
    return ds_by_model
