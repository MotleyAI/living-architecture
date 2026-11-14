class A:
    async def get_dataset(self, x: int) -> None: ...


class B(A):
    async def get_dataset(self, x: int) -> None: ...


async def f() -> None:
    a = A()
    await a.get_dataset(1)
