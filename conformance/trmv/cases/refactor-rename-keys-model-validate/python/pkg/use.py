from pkg.models import Model, Sub

a = Model.model_validate({"columns": []})
b = Model(**{'columns': []})
c = Sub.model_validate({"columns": [], "extra": 1})
d = Model.model_construct(**{"columns": []})
