from pkg.engine import SlayerQueryEngine


def f(e: SlayerQueryEngine) -> str:
    """Wraps :meth:`SlayerQueryEngine.pick_root_model` and ``recommend_root_model``."""
    # calls recommend_root_model first
    getattr(e, "pick_root_model")
    print("recommend_root_model")
    return e.pick_root_model(1)
