async def fetch() -> int:
    return 1


async def g() -> int:
    return await fetch() + await fetch()
