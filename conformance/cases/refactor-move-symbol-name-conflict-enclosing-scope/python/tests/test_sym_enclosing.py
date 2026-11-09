def test_sym_enclosing() -> None:
    pkg = "shadow"

    def inner() -> str:
        import pkg.a as pa

        return pa.f() + pkg

    assert inner()
