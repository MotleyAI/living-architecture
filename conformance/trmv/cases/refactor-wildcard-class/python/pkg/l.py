class Query:
    def run(self, name: str) -> str:
        model = name.upper()

        def inner() -> str:
            model = name.lower()
            return model

        return model + inner()

    def plan(self, name: str) -> str:
        model = name.title()
        return model


def load(name: str) -> str:
    model = name.strip()
    return model
