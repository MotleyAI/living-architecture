from pkg.c import take


def via_loop() -> None:
    for t in ("formula", "sql"):
        take(t)
