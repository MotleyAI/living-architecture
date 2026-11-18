class IntrospectedColumn:
    name: str = ""


class Ds:
    """Holds ``columns``."""

    columns: list[str] = []


# reads `columns`
def census_sql(columns: list[IntrospectedColumn]) -> str:
    """Joins ``columns``."""
    return ", ".join(c.name for c in columns)
