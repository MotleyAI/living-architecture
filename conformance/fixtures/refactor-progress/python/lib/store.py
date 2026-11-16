class Store:
    def load(self) -> int:
        return 1

    def drop(self) -> int:
        return 2

    def size(self) -> int:
        return 3

    def clear(self) -> int:
        return 4

    def save(self) -> int:
        return 5


class Other:
    def save(self) -> int:
        return 6
