from pathlib import Path

from trmv import typecheck
from trmv.config.command import command_argv, run_command


def trmv_typecheck(argv: list[str] | None = None) -> int:
    return run_command(
        "trmv-typecheck",
        command_argv(argv),
        lambda args: typecheck.run(
            cwd=Path.cwd(), write=args.write_baseline, language_id=args.language, realign_from=args.realign_from
        ),
    )
