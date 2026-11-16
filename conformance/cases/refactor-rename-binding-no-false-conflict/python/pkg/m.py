class O:
    next: int = 0


def call(**kw: int) -> None:
    print(kw)


old = 1


def use(o: O) -> int:
    # next is not read here
    call(next=old)
    return o.next + old


def unrelated() -> int:
    next = 3
    return next


def nested() -> int:
    def inner() -> int:
        next = 4
        return next

    return inner()
