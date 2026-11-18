from typing import NoReturn

from living_architecture import review
from living_architecture.cli import _argv


def la_fetch_failed_pr_checks(argv: list[str] | None = None) -> NoReturn:
    review.run_shim("la-fetch-failed-pr-checks", _argv(argv))
