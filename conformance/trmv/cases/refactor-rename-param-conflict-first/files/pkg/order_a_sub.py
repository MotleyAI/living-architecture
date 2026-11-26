from pkg.order_base import A

dataset_name = "d"


class B(A):
    def run(self, *, model_name: str) -> str:
        prefix = dataset_name
        return prefix + model_name + dataset_name
