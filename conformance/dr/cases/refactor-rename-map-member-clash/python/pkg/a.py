class Query:
    source: int = 0
    origin: int = 0


def use(q: Query) -> int:
    return q.source + q.origin
