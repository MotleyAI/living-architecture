async def load() -> int:
    return 1


async def g() -> int:
    return await load() + await load()
