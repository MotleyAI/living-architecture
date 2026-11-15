import argparse
from typing import Literal

from pkg.kinds import DriftKind

Other = Literal["edit_model", "zzz"]


def f(kind: DriftKind) -> None:
    print(kind)


def g(o: Other) -> None:
    print(o)


def run() -> None:
    f("edit_model")
    g("edit_model")
    s: str = "edit_model"
    parser = argparse.ArgumentParser()
    parser.add_argument("--kind", choices=["edit_model"])
    print(s, parser)
