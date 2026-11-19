def outer():
    import pkg.sub as sub

    def inner():
        nonlocal sub
        return sub.thing.X

    return inner
