import pkg.a as pa


def test_sym_alias_kept() -> None:
    assert pa.f() + pa.g()
