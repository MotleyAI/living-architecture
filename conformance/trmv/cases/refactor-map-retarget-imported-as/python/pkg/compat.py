from pkg.home import Target as Local

Alias = Local


def f() -> object:
    return Alias()
