from living_architecture import refactor
from living_architecture.cli import _argv, _run


def dr_mock_lint(argv: list[str] | None = None) -> int:
    return _run("dr-mock-lint", _argv(argv), lambda args: refactor.run_mock_lint(paths=args.paths, base=args.base))
