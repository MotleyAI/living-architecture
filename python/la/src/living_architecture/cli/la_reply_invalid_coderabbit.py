from typing import NoReturn

from living_architecture import review
from trmv.config.command import command_argv


def la_reply_invalid_coderabbit(argv: list[str] | None = None) -> NoReturn:
    review.run_shim("la-reply-invalid-coderabbit", command_argv(argv))
