class Model:
    name: str = ""


FIND = "MATCH (m:Model) RETURN m.name"
