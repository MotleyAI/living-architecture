from pkg.models import Model

a = Model.model_validate({"columns": []})
b = Model(columns=[])
