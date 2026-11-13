from pkg.models import ModelDict, Other

a = Other.model_validate({"columns": []})
b = Other(columns=[])
t: ModelDict = {"columns": []}
