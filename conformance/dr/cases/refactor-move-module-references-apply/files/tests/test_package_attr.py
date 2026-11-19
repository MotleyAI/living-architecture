import pkg.sql as sql_pkg
import pkg.database.client


def test_package_attr() -> None:
    assert pkg.database.client.X == 1 and sql_pkg.VERSION
