from pathlib import Path

from living_architecture import typecheck
from living_architecture.cli import _argv, _run


def la_typecheck(argv: list[str] | None = None) -> int:
    return _run(
        "la-typecheck",
        _argv(argv),
        lambda args: typecheck.run(
            cwd=Path.cwd(), write=args.write_baseline, language_id=args.language, realign_from=args.realign_from
        ),
    )
