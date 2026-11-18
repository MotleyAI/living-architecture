from typing import NoReturn

from living_architecture import review
from living_architecture.cli import _argv


def la_pr_reviewers(argv: list[str] | None = None) -> NoReturn:
    review.run_shim("la-pr-reviewers", _argv(argv))
