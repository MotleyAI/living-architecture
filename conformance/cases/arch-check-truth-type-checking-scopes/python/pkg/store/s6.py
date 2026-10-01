from typing import TYPE_CHECKING

FLAGS = [(TYPE_CHECKING := x) for x in ()]
if TYPE_CHECKING:
    from pkg.api import handlers
