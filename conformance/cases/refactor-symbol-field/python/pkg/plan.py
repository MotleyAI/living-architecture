class _ProjectionPlan:
    measures: list[str] = []
    dimensions: list[str] = []


measures = ["module-level"]


def count(plan: _ProjectionPlan) -> int:
    return len(plan.measures) + len(measures)
