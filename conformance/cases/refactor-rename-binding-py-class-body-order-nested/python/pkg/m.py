def outer() -> int:
    old = 1

    class C:
        total = old
        next = 2

    return C.total
