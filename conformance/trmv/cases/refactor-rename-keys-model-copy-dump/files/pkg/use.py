from pkg.models import Model


def f(m: Model) -> object:
    return (
        m.model_copy(update={"fields": []}),
        m.model_dump(exclude={"fields"}),
        m.model_dump_json(include={"fields": True, "label": True}),
    )
