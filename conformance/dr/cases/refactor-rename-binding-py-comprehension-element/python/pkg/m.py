old = 1


def f() -> list[int]:
    return [old + next for next in range(3)]
