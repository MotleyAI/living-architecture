from typing import NoReturn

from deterministic_refactor.config.command import command_argv
from living_architecture import review


def la_reply_invalid_coderabbit(argv: list[str] | None = None) -> NoReturn:
    review.run_shim("la-reply-invalid-coderabbit", command_argv(argv))
