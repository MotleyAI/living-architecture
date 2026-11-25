from pkg.a import A


def make() -> A:
    return A()


class Holder:
    store: A

    def __init__(self, s: A) -> None:
        self.s: A = s

    def run(self) -> int:
        return self.s.get_model() + self.store.get_model()


def calls(a: A, o: object) -> int:
    x = A()
    total = a.get_model() + make().get_model() + x.get_model()
    if isinstance(o, A):
        total += o.get_model()
    return total
