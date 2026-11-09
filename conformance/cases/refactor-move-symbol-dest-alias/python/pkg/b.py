from pkg.a import foo as bar


def child():
    return bar() + 1
