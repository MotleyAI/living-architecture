from deterministic_refactor.config.command import command_argv, run_command
from living_architecture import conventions


def la_count_comments(argv: list[str] | None = None) -> int:
    raw = command_argv(argv)
    return run_command("la-count-comments", raw, lambda _args: conventions.count_comments(raw))
