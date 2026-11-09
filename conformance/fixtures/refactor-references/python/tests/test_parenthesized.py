from pkg.sql import (
    dialects,  # the dialect table
    client,  # the client
    engine_factory,  # builds engines
)


def test_parenthesized() -> None:
    assert client.X and dialects.D and engine_factory.make()
