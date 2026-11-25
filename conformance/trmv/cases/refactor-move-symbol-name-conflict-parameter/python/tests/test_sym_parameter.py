def test_sym_parameter(pkg: object) -> None:
    import pkg.a as pa

    assert pa.f() and pkg
