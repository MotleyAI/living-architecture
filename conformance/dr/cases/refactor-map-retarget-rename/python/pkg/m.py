def target() -> int:
    return 1


old_alias = target


def f() -> int:
    return old_alias()
