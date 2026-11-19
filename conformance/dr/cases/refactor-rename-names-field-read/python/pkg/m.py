from pydantic import BaseModel


class Ds(BaseModel):
    columns: list[str] = []


def infos() -> list[object]:
    out: list[object] = []
    for f in ("columns",):
        out.append(Ds.model_fields[f])
    return out
