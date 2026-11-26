from pkg.models import Model


class Model2(Model):
    @classmethod
    def make(cls) -> "Model2":
        return cls(fields=[])
