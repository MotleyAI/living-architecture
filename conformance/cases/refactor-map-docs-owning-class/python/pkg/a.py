class Table:
    """A table and its ``columns``."""

    columns: list[str] = []

    def width(self) -> int:
        """The number of ``columns``."""
        return len(self.columns)

    class Meta:
        """Options of the table's ``columns``."""


class Result:
    """A result and its ``columns``."""

    columns: list[str] = []

    def width(self) -> int:
        # `columns` are counted
        return len(self.columns)
