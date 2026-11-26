from typing import NoReturn

from living_architecture import review
from trmv.config.command import command_argv


def la_reply_to_pr_thread(argv: list[str] | None = None) -> NoReturn:
    review.run_shim("la-reply-to-pr-thread", command_argv(argv))
