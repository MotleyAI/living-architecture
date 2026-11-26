from pkg.models import Model

a = Model.model_validate({"col" "umns": []})
b = Model.model_validate({"\x63olumns": []})
c = Model.model_validate({f"columns": []})
d = Model.model_validate({r'fields': []})
