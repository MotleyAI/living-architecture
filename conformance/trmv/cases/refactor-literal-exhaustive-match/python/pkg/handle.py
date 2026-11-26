from typing import assert_never

from pkg.kinds import DriftKind


def handle(kind: DriftKind) -> int:
    match kind:
        case "edit_model":
            return 1
        case "drop":
            return 2
        case _:
            assert_never(kind)
