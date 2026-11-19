import argparse

from deterministic_refactor import twin
from deterministic_refactor.config.command import command_argv, command_root
from living_architecture import archcheck
from living_architecture.config import run_command


def _arch_check(args: argparse.Namespace) -> int:
    language = args.language or (twin.NATIVE_LANGUAGE if args.emit else None)
    return archcheck.run(command_root(args.root), language=language, emit=args.emit, top_level=args.top_level)


def la_arch_check(argv: list[str] | None = None) -> int:
    return run_command("la-arch-check", command_argv(argv), _arch_check)
