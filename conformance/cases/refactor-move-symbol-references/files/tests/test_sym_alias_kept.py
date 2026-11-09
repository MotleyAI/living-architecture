import pkg.a as pa
import pkg.b


def test_sym_alias_kept() -> None:
    assert pkg.b.f() + pa.g()
