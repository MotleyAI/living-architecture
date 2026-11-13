class A:
    def get_model(self) -> int:
        return 1


def f(a: A, /, *, b: A) -> None:
    print(a.get_model() + b.get_model())
