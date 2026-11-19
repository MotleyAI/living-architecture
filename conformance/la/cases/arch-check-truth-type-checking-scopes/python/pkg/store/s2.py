from typing import TYPE_CHECKING


class C:
    TYPE_CHECKING = False


if TYPE_CHECKING:
    import pkg.api
