column = 1


def get_columns() -> int:
    return column


class ColumnCycleError(Exception):
    pass
