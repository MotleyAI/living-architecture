from pkg.kinds import DriftKind


def f(kind: DriftKind) -> None:
    print(kind)


def g() -> DriftKind:
    return "edit_master"


def h(kind: DriftKind = "edit_master") -> list[DriftKind]:
    k: DriftKind = 'edit_master'
    xs: list[DriftKind] = ["edit_master"]
    f("edit_master")
    return [k, *xs, kind]


def eq(kind: DriftKind) -> bool:
    return kind == "edit_master"


def isin(kind: DriftKind) -> bool:
    return kind in ("edit_master",)


def matched(kind: DriftKind) -> bool:
    match kind:
        case "edit_master":
            return True
        case _:
            return False
