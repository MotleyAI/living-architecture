from typing import NoReturn

from deterministic_refactor.config.command import command_argv
from living_architecture import review


def la_reply_to_pr_thread(argv: list[str] | None = None) -> NoReturn:
    review.run_shim("la-reply-to-pr-thread", command_argv(argv))
