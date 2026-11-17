try:
    import json
except ImportError:
    json = None


def f() -> str:
    return str(json)
