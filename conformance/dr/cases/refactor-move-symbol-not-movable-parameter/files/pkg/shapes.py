from typing import TYPE_CHECKING
import os.path

if TYPE_CHECKING:
    Alias = int

a, b = 1, 2
x = 1; y = 2
twice = 1
twice = 2


class K:
    def method(self, param: int) -> int:
        local = param + 1
        return local
