from pkg.engine import Engine


def run(engine: Engine) -> None:
    engine.save(engine.get_model())
