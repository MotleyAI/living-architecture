import os


class Base:
    pass


def tag(cls):
    return cls


if os.sep:
    Mixin, Other = object, object


SEP = os.sep
