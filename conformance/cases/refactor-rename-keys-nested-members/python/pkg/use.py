from pkg.models import Holder, Model

a = Model.model_validate({"columns": [{"name": "a", "type": "INT"}]})
b = Model(columns=[{"type": "INT"}])
c = Holder.model_validate({
    "by_name": {"x": {"type": "INT"}},
    "maybe": {"type": "INT"},
    "seq": [{"type": "INT"}],
    "tup": ({"type": "INT"},),
    "group": [{"type": "INT"}],
    "frozen": [{"type": "INT"}],
    "model": {"columns": [{"type": "INT"}]},
})
