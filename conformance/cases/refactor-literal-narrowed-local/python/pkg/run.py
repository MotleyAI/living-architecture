from pkg.kinds import DriftKind


def f(kind: DriftKind) -> None:
    print(kind)


def run() -> None:
    k = "edit_model"
    f(k)
