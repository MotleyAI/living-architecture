from pkg.kinds import f


def run(c: bool) -> None:
    v = "edit_model" if c else "drop"
    f(v)
