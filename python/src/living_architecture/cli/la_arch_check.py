import argparse

from living_architecture import archcheck, twin
from living_architecture.cli import _argv, _root, _run


def _arch_check(args: argparse.Namespace) -> int:
    language = args.language or (twin.NATIVE_LANGUAGE if args.emit else None)
    return archcheck.run(_root(args.root), language=language, emit=args.emit, top_level=args.top_level)


def la_arch_check(argv: list[str] | None = None) -> int:
    return _run("la-arch-check", _argv(argv), _arch_check)
