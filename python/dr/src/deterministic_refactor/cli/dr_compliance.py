from deterministic_refactor import refactor
from deterministic_refactor.config.command import command_argv, run_command


def dr_compliance(argv: list[str] | None = None) -> int:
    return run_command(
        "dr-compliance", command_argv(argv), lambda args: refactor.run_compliance(paths=args.paths, select=args.select, attrs=args.attr)
    )
