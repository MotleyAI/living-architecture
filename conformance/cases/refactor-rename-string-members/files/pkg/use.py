from pkg.engine import SlayerQueryEngine


class Cfg:
    def setattr(self, o: object, n: str) -> None: ...


def getattr(o: object, n: str) -> object:
    return o


def f(engine: SlayerQueryEngine, cfg: Cfg) -> None:
    getattr(engine, "save_model")
    cfg.setattr(engine, "save_model")
