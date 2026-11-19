from deterministic_refactor import refactor
from deterministic_refactor.config.command import command_argv, run_command


def dr_mock_lint(argv: list[str] | None = None) -> int:
    return run_command("dr-mock-lint", command_argv(argv), lambda args: refactor.run_mock_lint(paths=args.paths, base=args.base))
