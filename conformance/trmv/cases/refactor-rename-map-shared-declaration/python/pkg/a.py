class Query:
    source: int = 0


class Request:
    source: int = 0


def use(q: Query, r: Request) -> int:
    return q.source + r.source
