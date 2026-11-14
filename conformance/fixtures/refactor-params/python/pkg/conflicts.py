dataset_name = "d"


def g(*, model_name: str, dataset_name: str) -> str:
    return model_name + dataset_name


def h(*, model_name: str) -> str:
    return dataset_name + model_name


def k(*, model_name: str) -> str:
    dataset_name = model_name.upper()
    return dataset_name
