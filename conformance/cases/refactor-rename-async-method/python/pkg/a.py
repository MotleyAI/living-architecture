class A:
    async def get_model(self, x: int) -> None: ...


class B(A):
    async def get_model(self, x: int) -> None: ...


async def f() -> None:
    a = A()
    await a.get_model(1)
