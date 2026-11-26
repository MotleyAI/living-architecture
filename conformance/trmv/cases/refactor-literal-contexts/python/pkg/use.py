from pkg.kinds import DriftKind


def f(kind: DriftKind) -> None:
    print(kind)


def g() -> DriftKind:
    return "edit_model"


def h(kind: DriftKind = "edit_model") -> list[DriftKind]:
    k: DriftKind = 'edit_model'
    xs: list[DriftKind] = ["edit_model"]
    f("edit_model")
    return [k, *xs, kind]


def eq(kind: DriftKind) -> bool:
    return kind == "edit_model"


def isin(kind: DriftKind) -> bool:
    return kind in ("edit_model",)


def matched(kind: DriftKind) -> bool:
    match kind:
        case "edit_model":
            return True
        case _:
            return False
