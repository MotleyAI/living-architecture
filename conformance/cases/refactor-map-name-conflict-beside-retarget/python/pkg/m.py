def target() -> int:
    return 1


old_alias = target
spare = 2


def f() -> int:
    return old_alias()


def g() -> int:
    taken = 3
    return spare + taken
