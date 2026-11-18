import pkg.sub as sub


def f():
    global sub
    value = sub.thing.X
    return value


def outer():
    import pkg.sub as sub

    def inner():
        nonlocal sub
        return sub.thing.X

    return inner, sub
