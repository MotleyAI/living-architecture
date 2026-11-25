def outer(n: int) -> int:
    total = n

    def inner() -> int:
        nonlocal total
        total += 1
        return total

    for total in range(3):
        pass
    return inner() + sum(total for total in range(2))
