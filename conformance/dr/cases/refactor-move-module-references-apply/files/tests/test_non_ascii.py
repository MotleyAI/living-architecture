greeting = "héllo 😀"; from pkg.database.client import X


def test_non_ascii() -> None:
    assert X == 1 and greeting
