from operator import attrgetter

from pkg.store import Storage


def f(s: Storage) -> object:
    slow = "get_model is slow"
    return attrgetter("get_model")(s), getattr(s, "get_model"), s.get_model("a"), slow
