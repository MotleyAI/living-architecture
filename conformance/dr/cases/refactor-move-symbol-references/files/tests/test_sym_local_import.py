def test_sym_local_import() -> None:
    from pkg.b import f  # ALLOW(import-not-top)

    assert f()
