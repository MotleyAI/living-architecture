from typing import NoReturn

from deterministic_refactor.config.command import command_argv
from living_architecture import review


def la_pr_reviewers(argv: list[str] | None = None) -> NoReturn:
    review.run_shim("la-pr-reviewers", command_argv(argv))
