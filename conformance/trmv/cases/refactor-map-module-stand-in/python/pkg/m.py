class A:
    def save(self) -> int:
        return 1


class Other:
    def save(self) -> int:
        return 2


def use(a: A, o: Other) -> int:
    return a.save() + o.save()
