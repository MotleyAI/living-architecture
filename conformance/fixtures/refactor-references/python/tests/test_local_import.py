def test_local_import() -> None:
    from pkg.sql import client  # ALLOW(import-not-top)

    assert client.X == 1
