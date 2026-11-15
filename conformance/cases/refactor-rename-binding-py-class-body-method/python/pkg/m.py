old = 1


class C:
    next = 2

    def m(self) -> int:
        return old + self.next
