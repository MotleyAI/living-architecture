import os


class Base:
    pass


def tag(cls):
    return cls


if os.sep:
    Mixin, Other = object, object


@tag
class Child(Base, Mixin):
    SEP = "/"
    PATH = SEP

    def make(self) -> "Child":
        return Child()


SEP = os.sep
