def scan(data: list[int]) -> int:
    squares = [last := v * v for v in data]
    pairs = {i: (j := i + 1) for i in data if (k := i)}
    nested = [[w := a + b for b in data] for a in data]
    return last + j + k + w + len(squares) + len(pairs) + len(nested)


total = sum(t for t in range(3) if (seen := t))
print(seen, total)
