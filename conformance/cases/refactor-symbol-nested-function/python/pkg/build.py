def inner() -> int:
    return 1


def build() -> int:
    def inner() -> int:
        return 2

    return inner() + 1


def other() -> int:
    return inner()
