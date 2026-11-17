import os.path
import json as js
from . import sibling
from ..parent import thing as other
from collections import *
from typing import TYPE_CHECKING

__all__ = ["Counter", "run"]

counter = 0
flag: bool
limit: int = 3


def run(*args, key=None, **kwargs):
    global counter
    counter += 1
    total = 0

    def inner():
        nonlocal total
        total += 1
        return total

    with open(os.path.join("a", "b")) as fh, open("c") as (g):
        data = js.load(fh)
    try:
        pass
    except (OSError, ValueError) as error:
        print(error)
    for index, item in enumerate(args):
        del item
    lam = lambda q, r=limit: q + r
    return inner, data, lam, other, sibling


@staticmethod
def decorated(): ...


class Registry(dict, metaclass=type):
    entries = []
    while len(entries) < limit:
        entries.append(entries)
    for entry in entries:
        name = entry
    size = len(name)

    def method(self) -> "Registry":
        return Registry


if TYPE_CHECKING:
    Alias = int
