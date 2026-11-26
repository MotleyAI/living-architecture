from typing import NoReturn

from living_architecture import review
from trmv.config.command import command_argv


def la_fetch_failed_pr_checks(argv: list[str] | None = None) -> NoReturn:
    review.run_shim("la-fetch-failed-pr-checks", command_argv(argv))
