from living_architecture import refactor
from living_architecture.cli import _argv, _run


def dr_compliance(argv: list[str] | None = None) -> int:
    return _run(
        "dr-compliance", _argv(argv), lambda args: refactor.run_compliance(paths=args.paths, select=args.select, attrs=args.attr)
    )
