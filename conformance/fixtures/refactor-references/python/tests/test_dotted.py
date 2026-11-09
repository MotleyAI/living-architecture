import pkg.sql.client


def test_dotted() -> None:
    assert pkg.sql.client.X == 1
