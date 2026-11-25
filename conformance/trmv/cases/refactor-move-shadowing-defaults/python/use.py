import pkg.sub as sub


def f(sub: int = sub.thing.X):
    return sub


def g(sub: sub.thing.Kind) -> sub.thing.Kind:
    return sub


lam = lambda sub=sub.thing.X: sub
