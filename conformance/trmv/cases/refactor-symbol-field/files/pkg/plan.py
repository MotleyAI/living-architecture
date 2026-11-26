class _ProjectionPlan:
    metrics: list[str] = []
    dimensions: list[str] = []


measures = ["module-level"]


def count(plan: _ProjectionPlan) -> int:
    return len(plan.metrics) + len(measures)
