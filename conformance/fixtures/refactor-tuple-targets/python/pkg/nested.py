def nested(s: tuple[tuple[int, int], int]) -> tuple[int, int]:
    (a, b), c = s
    return b, c
