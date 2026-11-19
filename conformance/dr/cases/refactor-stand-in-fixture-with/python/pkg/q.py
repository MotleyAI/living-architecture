class Query:
    def root_model(self) -> str:
        return "q"


class Plan:
    def root_model(self) -> str:
        return "p"


class Fake:
    def root_model(self) -> str:
        return "f"
