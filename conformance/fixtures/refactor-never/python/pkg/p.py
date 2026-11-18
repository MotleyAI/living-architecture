from typing import Optional

from pydantic import BaseModel


class Attach(BaseModel):
    producer_root_model: Optional[str] = None


class Plan(BaseModel):
    attach_plans: list[Attach] = []


def roots(planned, root: Optional[str] = None) -> list[Optional[str]]:
    attaches = list(getattr(planned, "attach_plans", ()) or ())
    out: list[Optional[str]] = []
    for a in attaches:
        out.append(a.producer_root_model or root)
    return out


def more(planned) -> list[object]:
    g = getattr(planned, "attach_plans", ())
    first = list(g)[0].producer_root_model
    return [first, *[k.producer_root_model for k in list(g)]]


def typed(plan: Plan) -> list[Optional[str]]:
    return [a.producer_root_model for a in plan.attach_plans]
