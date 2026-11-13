def kwonly(*, dataset_name: str) -> str:
    return dataset_name


def star(*xs: int, model_name: str) -> str:
    return model_name + str(len(xs))


def posonly(model_name: str, /) -> str:
    return model_name
