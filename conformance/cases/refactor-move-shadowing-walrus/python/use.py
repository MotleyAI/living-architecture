import pkg.sub as sub

print(sub.thing.X)


def f(xs):
    [(sub := v) for v in xs]
    return sub.thing.X
