import pkg.database.client as client


def test_self_alias() -> None:
    assert client.X == 1
