class O:
    dataset_name: str = ""


def other(*, dataset_name: int) -> None:
    print(dataset_name)


def m(*, model_name: str, o: O) -> str:
    other(dataset_name=1)
    return o.dataset_name + model_name
