from pkg.c import take


class K:
    FORMULA = "formula"


def via_class() -> None:
    take(K.FORMULA)
