from trmv import refactor
from trmv.config.command import command_argv, run_command


def trmv_compliance(argv: list[str] | None = None) -> int:
    return run_command(
        "trmv-compliance", command_argv(argv), lambda args: refactor.run_compliance(paths=args.paths, select=args.select, attrs=args.attr)
    )
