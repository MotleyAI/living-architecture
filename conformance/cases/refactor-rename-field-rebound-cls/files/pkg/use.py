from pkg.models import Model, Other


class Model2(Model):
    @classmethod
    def make(cls) -> object:
        cls = Other
        return cls(columns=[])


class Plain:
    @classmethod
    def model_construct(cls, columns: list[int]) -> "Plain":
        return cls()


p = Plain.model_construct(columns=[])
