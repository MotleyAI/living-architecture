class Store:
    def save_model(self) -> None:
        pass


class Engine:
    def save_model(self) -> None:
        pass

    def save(self) -> None:
        return self.save_model()
