def f(name: str) -> str:
    model = name.upper()
    return model


def g(name: str) -> str:
    model = name.lower()
    return model


def k(name: str) -> str:
    dataset = name
    model = name.title()
    return model + dataset
