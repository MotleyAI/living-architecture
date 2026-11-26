from typing import TYPE_CHECKING


class C:
    TYPE_CHECKING = False

    def m(self):
        if TYPE_CHECKING:
            import pkg.api
