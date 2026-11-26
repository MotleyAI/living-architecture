from living_architecture import conventions
from living_architecture.config import run_command
from trmv.config.command import command_argv


def la_count_comments(argv: list[str] | None = None) -> int:
    raw = command_argv(argv)
    return run_command("la-count-comments", raw, lambda _args: conventions.count_comments(raw))
