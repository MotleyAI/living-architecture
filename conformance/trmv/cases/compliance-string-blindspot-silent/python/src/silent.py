def t(m) -> object:
    return hasattr(m, "formula")


def u(m) -> object:
    return getattr(m, "formula", None)
