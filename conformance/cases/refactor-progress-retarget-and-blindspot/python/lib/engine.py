class Engine:
    def persist_model(self) -> int:
        return 1

    def persist(self) -> int:
        return self.persist_model()


class Fast(Engine):
    def persist(self) -> int:
        return 2
