import typing


def f(typing):
    return typing


if typing.TYPE_CHECKING:
    import pkg.api
