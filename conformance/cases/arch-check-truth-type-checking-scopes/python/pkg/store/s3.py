from typing import TYPE_CHECKING

FLAGS = [TYPE_CHECKING for TYPE_CHECKING in ()]
if TYPE_CHECKING:
    import pkg.api
