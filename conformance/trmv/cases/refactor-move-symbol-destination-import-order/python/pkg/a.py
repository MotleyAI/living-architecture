from __future__ import annotations

from .c import C
import yaml
import json


def g() -> int:
    return 1


def f(c: C) -> C:
    print(json.dumps(yaml.safe_load("1")), g())
    return c
