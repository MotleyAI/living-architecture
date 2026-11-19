old = 1


def outer() -> int:
    next = 0

    def inner() -> int:
        nonlocal next
        next += 1
        return old + next

    return inner()
