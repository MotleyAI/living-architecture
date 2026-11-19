dataset_name = "d"


class A:
    def run(self, *, model_name: str) -> str:
        return model_name + dataset_name
