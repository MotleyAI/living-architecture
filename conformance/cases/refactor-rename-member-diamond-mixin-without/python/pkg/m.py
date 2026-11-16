class A:
    def run(self) -> int:
        return 1


class B(A):
    def run(self) -> int:
        return 2


class C(A):
    def run(self) -> int:
        return 3


class D(B, C):
    def run(self) -> int:
        return super().run()


class M:
    def run(self) -> int:
        return 4


class E(M, A):
    pass


def use(a: A, d: D, e: E) -> int:
    return a.run() + d.run() + e.run()
