class Model:
    pass


class Engine:
    def save_model(self, m: Model) -> None:
        pass

    def save(self, m: Model) -> None:
        return self.save_model(m)
