class A:
    def execute(self) -> int:
        return 1


class B(A):
    def execute(self) -> int:
        return super().execute() + 1


def calls(a: A, b: B) -> int:
    return a.execute() + b.execute()
