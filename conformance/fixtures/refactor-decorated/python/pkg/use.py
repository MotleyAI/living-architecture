from pkg.h import C, engine, plain, sync_engine, wrapped


async def f(c: C) -> None:
    async with engine(models=[1]) as e:
        print(e)
    with sync_engine(models=[1]) as s:
        print(s)
    with c.scope(models=[1]) as t:
        print(t)
    print(plain(models=[1]), wrapped(models=[1]))
