from pkg import mod


class Engine:
    def list_models(self) -> list[str]:
        return []


def test_a(engine: Engine) -> None:
    assert callable(getattr(engine, "list_models"))
    assert callable(getattr(mod, "list_datasets"))
