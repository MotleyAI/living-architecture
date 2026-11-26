class Base(Exception):
    def __init__(self, msg: str) -> None:
        super().__init__(msg)


class A(Base):
    def __init__(self, msg: str, *, field: str) -> None:
        self.field = field
        super().__init__(msg)


class B(Base):
    def __init__(self, msg: str, *, field: str) -> None:
        self.field = field
        super().__init__(f"field of {field}")


class C(A):
    def __init__(self, msg: str, *, field: str) -> None:
        super().__init__(msg, field=field)
