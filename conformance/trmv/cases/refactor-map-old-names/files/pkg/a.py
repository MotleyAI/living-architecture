class A:
    def new(self, y: int) -> int:
        return y


def call(a: A) -> int:
    return a.new(y=1)
