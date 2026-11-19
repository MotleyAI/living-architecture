from deterministic_refactor.config.command import command_argv, command_root
from living_architecture import c4
from living_architecture.config import run_command


def la_arch_migrate(argv: list[str] | None = None) -> int:
    return run_command("la-arch-migrate", command_argv(argv), lambda args: c4.run_migrate(command_root(args.root)))
