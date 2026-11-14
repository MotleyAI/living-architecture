class A:
    def run(self, model_name: str) -> str:
        return model_name


class B(A):
    def run(self, model_name: str) -> str:
        return model_name.upper()


def calls(a: A, b: B) -> str:
    return a.run(model_name="x") + b.run(model_name="y") + a.run("z")
