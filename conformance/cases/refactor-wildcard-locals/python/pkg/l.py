def f(name: str) -> str:
    model = name.upper()
    return model


class Q:
    def run(self, name: str) -> str:
        model = name.lower()
        return model


def k(name: str) -> str:
    def inner() -> str:
        model = name.strip()
        return model

    return inner()


def h(model: str) -> str:
    return model
