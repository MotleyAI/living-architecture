from pkg.hier_base import A


class B(A):
    def run(self, *, model_name: str) -> str:
        return super().run(model_name=model_name)


def calls(a: A, b: B) -> str:
    return a.run(model_name="x") + b.run(model_name="y")
