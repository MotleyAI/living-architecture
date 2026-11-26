from pkg.hier_base import A


class B(A):
    def run(self, *, dataset_name: str) -> str:
        return super().run(dataset_name=dataset_name)


def calls(a: A, b: B) -> str:
    return a.run(dataset_name="x") + b.run(dataset_name="y")
