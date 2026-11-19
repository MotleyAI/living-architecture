class IntrospectedColumn:
    name: str = ""


class Ds:
    columns: list[str] = []


def census_sql(columns: list[IntrospectedColumn]) -> str:
    return ", ".join(c.name for c in columns)


def field_names(columns: list[str]) -> list[str]:
    return columns
