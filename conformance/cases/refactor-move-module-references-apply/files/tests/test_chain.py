from pkg.database import client as sql_client
from pkg.sql import engine as sql_engine


def test_chain() -> None:
    assert sql_engine.client.X and sql_client.engine_factory.make()
