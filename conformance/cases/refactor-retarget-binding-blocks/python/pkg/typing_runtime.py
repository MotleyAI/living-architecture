from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pkg.compat import AcmeModel


def check(m: AcmeModel) -> None:
    print(m)


def make() -> object:
    from pkg.compat import AcmeModel
    return AcmeModel()
