def f() -> int:
    from .x import y
    import json

    return y + len(json.dumps(1))


def g() -> int:
    return 2
