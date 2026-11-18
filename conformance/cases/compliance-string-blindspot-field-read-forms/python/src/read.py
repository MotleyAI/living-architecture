def v(m) -> object:
    return m.model_fields.get("formula")


def w(m) -> bool:
    return "formula" in m.model_fields
