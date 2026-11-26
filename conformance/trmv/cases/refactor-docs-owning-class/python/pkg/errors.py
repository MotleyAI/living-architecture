class A:
    """Carries ``field``."""

    field: str = ""

    def show(self) -> str:
        # `field` is shown bare
        return self.field


class B:
    """Carries ``field``; a different class."""

    field: str = ""

    def describe(self) -> str:
        return f"field of {self.field}"
