from pkg.models import Holder, Model

a = Model.model_validate({"columns": [{"name": "a", "kind": "INT"}]})
b = Model(columns=[{"kind": "INT"}])
c = Holder.model_validate({
    "by_name": {"x": {"kind": "INT"}},
    "maybe": {"kind": "INT"},
    "seq": [{"kind": "INT"}],
    "tup": ({"kind": "INT"},),
    "group": [{"kind": "INT"}],
    "frozen": [{"kind": "INT"}],
    "model": {"columns": [{"kind": "INT"}]},
})
