total = 0


def outer() -> int:
    b = 1

    def inner() -> int:
        b = 2
        return b

    squares = [b for b in range(3)]

    class Box:
        b = 3

    return b + inner() + len(squares) + Box.b


def bump() -> None:
    global total
    total += 1


def local_total() -> int:
    total = 5
    return total


def counter() -> int:
    shared = 1

    def step() -> int:
        nonlocal shared
        shared += 1
        own = shared
        return own

    own = step()
    return own + shared
