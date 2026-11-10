from . import dialects, engine_factory
from .dialects import D

X = 1


class Client:
    dialect = dialects.D or D

    def engine(self) -> str:
        return engine_factory.make()
