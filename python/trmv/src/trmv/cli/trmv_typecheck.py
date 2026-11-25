from pathlib import Path

from deterministic_refactor import typecheck
from deterministic_refactor.config.command import command_argv, run_command


def dr_typecheck(argv: list[str] | None = None) -> int:
    return run_command(
        "dr-typecheck",
        command_argv(argv),
        lambda args: typecheck.run(
            cwd=Path.cwd(), write=args.write_baseline, language_id=args.language, realign_from=args.realign_from
        ),
    )
