from pkg.engine import SlayerQueryEngine


def f(e: SlayerQueryEngine) -> str:
    """Wraps :meth:`SlayerQueryEngine.recommend_root_model` and ``recommend_root_model``."""
    # calls recommend_root_model first
    getattr(e, "recommend_root_model")
    print("recommend_root_model")
    return e.recommend_root_model(1)
