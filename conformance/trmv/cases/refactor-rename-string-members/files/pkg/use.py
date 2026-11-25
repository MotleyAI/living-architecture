from pkg.engine import SearchQueryEngine


class Cfg:
    def setattr(self, o: object, n: str) -> None: ...


def getattr(o: object, n: str) -> object:
    return o


def f(engine: SearchQueryEngine, cfg: Cfg) -> None:
    getattr(engine, "save_model")
    cfg.setattr(engine, "save_model")
