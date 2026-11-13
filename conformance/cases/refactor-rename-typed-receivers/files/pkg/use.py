from pkg.a import A


def make() -> A:
    return A()


class Holder:
    store: A

    def __init__(self, s: A) -> None:
        self.s: A = s

    def run(self) -> int:
        return self.s.get_dataset() + self.store.get_dataset()


def calls(a: A, o: object) -> int:
    x = A()
    total = a.get_dataset() + make().get_dataset() + x.get_dataset()
    if isinstance(o, A):
        total += o.get_dataset()
    return total
