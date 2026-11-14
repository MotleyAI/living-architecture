from pkg.engine import AcmeQueryEngine


def f(e: AcmeQueryEngine) -> str:
    """Wraps :meth:`AcmeQueryEngine.recommend_root_model` and ``recommend_root_model``."""
    # calls recommend_root_model first
    getattr(e, "recommend_root_model")
    print("recommend_root_model")
    return e.recommend_root_model(1)
