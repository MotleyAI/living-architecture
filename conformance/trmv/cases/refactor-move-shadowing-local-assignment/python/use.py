def f():
    import pkg.sub as sub

    value = sub.thing.X
    sub = None
    return value, sub
