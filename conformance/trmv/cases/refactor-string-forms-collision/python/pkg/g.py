class Model:
    name: str = ""


SCHEMA = "CREATE NODE TABLE Model(name STRING, PRIMARY KEY(name))"
FIND = "MATCH (m:Model) RETURN m.name"
