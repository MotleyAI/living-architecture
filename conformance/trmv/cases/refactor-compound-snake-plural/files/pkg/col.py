field = 1


def get_columns() -> int:
    return field


class ColumnCycleError(Exception):
    pass
