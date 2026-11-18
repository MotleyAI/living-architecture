from deterministic_refactor.config.command import command_argv, command_root, run_command
from living_architecture import c4


def la_arch_diagrams(argv: list[str] | None = None) -> int:
    return run_command("la-arch-diagrams", command_argv(argv), lambda args: c4.run(command_root(args.root)))
