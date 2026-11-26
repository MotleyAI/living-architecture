class A:
    def sync_dataset(self, x: int) -> int:
        return x


class B(A):
    def sync_dataset(self, x: int) -> int:
        return super().sync_dataset(x)
