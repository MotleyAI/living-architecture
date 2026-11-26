from typing import NoReturn

from living_architecture import review
from trmv.config.command import command_argv


def la_pr_reviewers(argv: list[str] | None = None) -> NoReturn:
    review.run_shim("la-pr-reviewers", command_argv(argv))
