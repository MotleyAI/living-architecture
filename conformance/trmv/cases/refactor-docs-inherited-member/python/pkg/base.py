class Base:
    field: str = ""


class Sub(Base):
    """Reads ``field`` of the base."""


class Other:
    field: str = ""


class Mixed(Other, Base):
    """Reads ``field`` of the other."""
