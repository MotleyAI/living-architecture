from pkg.q import Sub, bound, lit, other, q, q2, shadow


def test_it() -> None:
    assert q(measures=["n"]).source_model == "orders"
    q2(measures=["n"])
    Sub(measures=[])
    lit(measures=["n"])
    bound(measures=["n"])
    shadow(measures=["n"])
    other(measures=[])
