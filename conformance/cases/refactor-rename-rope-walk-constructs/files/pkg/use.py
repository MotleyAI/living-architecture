import sys

from pkg.api import field

label = field(description="(")


def trampoline(body: str) -> str:
    return f"#!/bin/sh\n'''exec' '{field(description=sys.executable)}' \"$0\" \"$@\"\n' '''\n{body}"


quoted = f'{field(description=label)}"""{field(description="x")}'
