from typing import NoReturn

from living_architecture import review
from trmv.config.command import command_argv


def la_wait_for_reviews(argv: list[str] | None = None) -> NoReturn:
    review.run_shim("la-wait-for-reviews", command_argv(argv))
