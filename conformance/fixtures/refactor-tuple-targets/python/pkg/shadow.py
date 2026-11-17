def f(s: tuple[str, str], xs: list[str]) -> tuple[list[str], str]:
    a, model_name = s
    return [model_name for model_name in xs], model_name
