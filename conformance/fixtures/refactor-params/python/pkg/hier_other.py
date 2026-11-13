class Base:
    def run(self, *, model_name: str) -> str:
        return model_name


class Renamed(Base):
    def run(self, *, name: str) -> str:  # pyright: ignore[reportIncompatibleMethodOverride]
        return name
