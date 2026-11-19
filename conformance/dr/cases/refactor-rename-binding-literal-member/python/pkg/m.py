from typing import Literal

Kind = Literal["fast", "slow"]


def f(k: Kind) -> bool:
    nxt = 1
    return k == "fast" and nxt > 0
