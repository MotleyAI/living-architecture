class A:
    def old(self, x: int) -> int:
        return x


def call(a: A) -> int:
    return a.old(x=1)
