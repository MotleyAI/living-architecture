import pkg.sql as sql_pkg


def test_package_attr() -> None:
    assert sql_pkg.client.X == 1 and sql_pkg.VERSION
