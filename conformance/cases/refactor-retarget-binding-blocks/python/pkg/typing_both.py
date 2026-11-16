from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pkg.models import Model
    from pkg.compat import AcmeModel


def check(m: AcmeModel, n: Model) -> None:
    print(m, n)
