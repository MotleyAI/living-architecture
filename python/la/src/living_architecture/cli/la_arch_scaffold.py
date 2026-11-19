from deterministic_refactor.config.command import command_argv, command_root
from living_architecture import archcheck
from living_architecture.config import run_command


def la_arch_scaffold(argv: list[str] | None = None) -> int:
    return run_command("la-arch-scaffold", command_argv(argv), lambda args: archcheck.run_scaffold(command_root(args.root)))
