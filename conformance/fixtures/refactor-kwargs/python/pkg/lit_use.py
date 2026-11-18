from pkg.q import Query, q


def unpacked() -> Query:
    return q(**{"measures": ["n"]})
