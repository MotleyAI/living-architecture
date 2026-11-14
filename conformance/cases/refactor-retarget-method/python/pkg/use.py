from pkg.engine import Engine, Model


def run(engine: Engine, m: Model) -> None:
    engine.save(m)
