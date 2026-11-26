class Old:
    pass


def f(make: object) -> None:
    Next = 1
    x: "Old" = make
    print(Next, x)
