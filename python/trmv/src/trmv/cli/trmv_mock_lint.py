from trmv import refactor
from trmv.config.command import command_argv, run_command


def trmv_mock_lint(argv: list[str] | None = None) -> int:
    return run_command("trmv-mock-lint", command_argv(argv), lambda args: refactor.run_mock_lint(paths=args.paths, base=args.base))
