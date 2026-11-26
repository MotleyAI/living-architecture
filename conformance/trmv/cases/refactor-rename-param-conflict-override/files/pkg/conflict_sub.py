from pkg.conflict_base import A

dataset_name = "d"


class B(A):
    def run(self, *, model_name: str) -> str:
        return dataset_name + model_name
