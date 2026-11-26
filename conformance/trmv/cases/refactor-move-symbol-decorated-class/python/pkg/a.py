import functools
from typing import final

X = 1

# About K.
# More.
@functools.total_ordering
# Between.
@final
class K:
    pass


def g() -> int:
    return X
