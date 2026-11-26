from pkg.sql import (
    dialects,  # the dialect table
    engine_factory,  # builds engines
)
from pkg.database import client


def test_parenthesized() -> None:
    assert client.X and dialects.D and engine_factory.make()
