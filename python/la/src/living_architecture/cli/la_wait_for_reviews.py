from typing import NoReturn

from living_architecture import review
from living_architecture.cli import _argv


def la_wait_for_reviews(argv: list[str] | None = None) -> NoReturn:
    review.run_shim("la-wait-for-reviews", _argv(argv))
