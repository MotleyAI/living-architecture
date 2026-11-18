class Q:
    def measures(self) -> int:
        return 1

    def metrics(self) -> int:
        return 2


def use(q: Q) -> int:
    return q.measures() + q.metrics()
