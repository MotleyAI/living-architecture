model_name = "m"


def pick(items: list[str]) -> list[str]:
    return sorted(items, key=lambda model: model)
