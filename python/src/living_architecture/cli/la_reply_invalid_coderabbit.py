from typing import NoReturn

from living_architecture import review
from living_architecture.cli import _argv


def la_reply_invalid_coderabbit(argv: list[str] | None = None) -> NoReturn:
    review.run_shim("la-reply-invalid-coderabbit", _argv(argv))
