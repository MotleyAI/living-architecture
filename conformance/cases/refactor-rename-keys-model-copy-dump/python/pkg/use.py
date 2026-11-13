from pkg.models import Model


def f(m: Model) -> object:
    return (
        m.model_copy(update={"columns": []}),
        m.model_dump(exclude={"columns"}),
        m.model_dump_json(include={"columns": True, "label": True}),
    )
