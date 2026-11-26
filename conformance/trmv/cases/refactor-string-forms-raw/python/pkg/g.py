class Model:
    name: str = ""


PLAIN = "MATCH (m:Model)"
ESCAPED = "MATCH (m:\x4dodel)"
ACCENT = "MATCH (m:Model) // modèle"
