from pkg.b import Base, Mixin, tag


@tag
class Child(Base, Mixin):
    SEP = "/"
    PATH = SEP

    def make(self) -> "Child":
        return Child()
