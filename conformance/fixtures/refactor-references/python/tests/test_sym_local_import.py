def test_sym_local_import() -> None:
    from pkg.a import f  # ALLOW(import-not-top)

    assert f()
