from typing import NoReturn

from deterministic_refactor.config.command import command_argv
from living_architecture import review


def la_wait_for_reviews(argv: list[str] | None = None) -> NoReturn:
    review.run_shim("la-wait-for-reviews", command_argv(argv))
