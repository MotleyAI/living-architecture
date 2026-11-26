from pkg.models import Model, Sub

a = Model.model_validate({"fields": []})
b = Model(**{'fields': []})
c = Sub.model_validate({"fields": [], "extra": 1})
d = Model.model_construct(**{"fields": []})
