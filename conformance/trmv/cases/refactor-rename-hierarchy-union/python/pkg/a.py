class A:
    def run(self) -> int:
        return 1


class B(A):
    def run(self) -> int:
        return super().run() + 1


def calls(a: A, b: B) -> int:
    return a.run() + b.run()
