class A:
    def sync_model(self, x: int) -> int:
        return x


class B(A):
    def sync_model(self, x: int) -> int:
        return super().sync_model(x)
