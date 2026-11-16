from pkg.store import Storage


def f(s: Storage) -> int:
    return s.get_model("a")
