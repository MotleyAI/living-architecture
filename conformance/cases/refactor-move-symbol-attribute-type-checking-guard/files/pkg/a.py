from __future__ import annotations

import settings

if settings.TYPE_CHECKING:
    from pkg.x import Widget


def f(w: Widget) -> None:
    return None
