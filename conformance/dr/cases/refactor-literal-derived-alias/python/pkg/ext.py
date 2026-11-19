from typing import Literal

from pkg.kinds import DriftKind

Ext = Literal[DriftKind, "x"]


def h(e: Ext) -> None:
    print(e)


def run() -> None:
    h("edit_model")
