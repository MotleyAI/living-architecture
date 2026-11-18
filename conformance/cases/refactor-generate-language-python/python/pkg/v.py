class Query:
    measures: list[str] = []


def add_measures(q: Query, measures: list[str]) -> None:
    q.measures += measures


def census_sql(columns: list[str]) -> str:
    return ", ".join(columns)
