from typing import TYPE_CHECKING
if TYPE_CHECKING: from pkg.a import f, g
try: from pkg.a import g, f
except ImportError: from pkg.a import f, g
if TYPE_CHECKING:
    pass
else: from pkg.a import f, g
try:
    pass
finally: x = 1; from pkg.a import f, g
