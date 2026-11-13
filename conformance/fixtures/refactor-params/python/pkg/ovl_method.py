from typing import overload


class A:
    @overload
    def run(self, *, model_name: str) -> str: ...
    @overload
    def run(self, *, model_name: int) -> int: ...
    def run(self, *, model_name: str | int) -> str | int:
        return model_name


class B(A):
    def run(self, *, model_name: str | int) -> str | int:  # pyright: ignore[reportIncompatibleMethodOverride]
        return model_name


def calls(a: A, b: B) -> object:
    return a.run(model_name="x"), b.run(model_name=1)
