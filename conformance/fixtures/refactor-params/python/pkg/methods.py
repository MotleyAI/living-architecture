class C:
    def kmeth(self, *, model_name: str) -> str:
        return model_name

    async def fetch(self, *, model_name: str) -> str:
        return model_name.upper()


def use(c: C) -> str:
    return c.kmeth(model_name="y")


async def ause(c: C) -> str:
    return await c.fetch(model_name="y")
