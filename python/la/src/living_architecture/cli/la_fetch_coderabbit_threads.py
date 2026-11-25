from typing import NoReturn

from living_architecture import review
from trmv.config.command import command_argv


def la_fetch_coderabbit_threads(argv: list[str] | None = None) -> NoReturn:
    review.run_shim("la-fetch-coderabbit-threads", command_argv(argv))
