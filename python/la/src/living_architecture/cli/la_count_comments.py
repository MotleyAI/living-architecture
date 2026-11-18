from living_architecture import conventions
from living_architecture.cli import _argv, _run


def la_count_comments(argv: list[str] | None = None) -> int:
    raw = _argv(argv)
    return _run("la-count-comments", raw, lambda _args: conventions.count_comments(raw))
