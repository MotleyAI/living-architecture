import pkg.sub as sub

print(sub.thing.X)
lam = lambda sub: sub.thing.X


def posonly(sub, /):
    return sub.thing.X


def plain(sub):
    return sub.thing.X


def kwonly(*, sub):
    return sub.thing.X


def star(*sub):
    return sub.thing.X


def dstar(**sub):
    return sub.thing.X


comp = [sub.thing.X for sub in [1]]
