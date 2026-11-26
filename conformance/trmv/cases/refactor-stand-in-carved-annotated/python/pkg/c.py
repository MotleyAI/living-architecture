class IntrospectedColumn:
    name: str = ""


class Ds:
    columns: list[str] = []


class Probe:
    columns: list[IntrospectedColumn] = []
