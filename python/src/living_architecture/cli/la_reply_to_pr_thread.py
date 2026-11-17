from typing import NoReturn

from living_architecture import review
from living_architecture.cli import _argv


def la_reply_to_pr_thread(argv: list[str] | None = None) -> NoReturn:
    review.run_shim("la-reply-to-pr-thread", _argv(argv))
