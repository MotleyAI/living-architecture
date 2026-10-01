import typing


def f():
    global typing
    typing = None


if typing.TYPE_CHECKING:
    import pkg.old
