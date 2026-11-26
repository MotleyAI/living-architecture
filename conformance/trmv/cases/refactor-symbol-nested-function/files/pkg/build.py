def inner() -> int:
    return 1


def build() -> int:
    def helper() -> int:
        return 2

    return helper() + 1


def other() -> int:
    return inner()
