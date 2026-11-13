def kwonly(*, model_name: str) -> str:
    return model_name


def star(*xs: int, model_name: str) -> str:
    return model_name + str(len(xs))


def posonly(model_name: str, /) -> str:
    return model_name
