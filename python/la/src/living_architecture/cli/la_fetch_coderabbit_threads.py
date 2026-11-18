from typing import NoReturn

from living_architecture import review
from living_architecture.cli import _argv


def la_fetch_coderabbit_threads(argv: list[str] | None = None) -> NoReturn:
    review.run_shim("la-fetch-coderabbit-threads", _argv(argv))
