class Unrelated:
    def get_model(self) -> str:
        return ""


def g(u: Unrelated) -> str:
    return u.get_model()
