class A:
    def save(self) -> int:
        return 1


class B:
    def save(self) -> int:
        return 2


def use(x):
    return x.save()
