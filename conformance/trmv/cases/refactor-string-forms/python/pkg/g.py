class Model:
    name: str = ""


class ModelColumn:
    name: str = ""


SCHEMA = "CREATE NODE TABLE Model(name STRING, PRIMARY KEY(name))"
FIND = "MATCH (m:Model) RETURN m.name"


def find(i: int) -> str:
    return f"MATCH (m:Model) WHERE m.id = {i}"


OTHER = "MATCH (m:ModelColumn)"
PROSE = "a Model in prose"
