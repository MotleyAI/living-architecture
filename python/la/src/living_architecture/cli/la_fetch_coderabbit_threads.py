from typing import NoReturn

from deterministic_refactor.config.command import command_argv
from living_architecture import review


def la_fetch_coderabbit_threads(argv: list[str] | None = None) -> NoReturn:
    review.run_shim("la-fetch-coderabbit-threads", command_argv(argv))
