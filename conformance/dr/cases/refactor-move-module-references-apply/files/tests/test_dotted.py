import pkg.database.client


def test_dotted() -> None:
    assert pkg.database.client.X == 1
