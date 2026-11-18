from typing import TYPE_CHECKING
if TYPE_CHECKING: from pkg.a import g; from pkg.b import f
try: from pkg.a import g; from pkg.b import f
except ImportError: from pkg.a import g; from pkg.b import f
if TYPE_CHECKING:
    pass
else: from pkg.a import g; from pkg.b import f
try:
    pass
finally: x = 1; from pkg.a import g; from pkg.b import f
