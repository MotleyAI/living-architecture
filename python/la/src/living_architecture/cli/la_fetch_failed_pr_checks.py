from typing import NoReturn

from deterministic_refactor.config.command import command_argv
from living_architecture import review


def la_fetch_failed_pr_checks(argv: list[str] | None = None) -> NoReturn:
    review.run_shim("la-fetch-failed-pr-checks", command_argv(argv))
