class A:
    @classmethod
    def cm(cls, *, model_name: str) -> str:
        return model_name

    @staticmethod
    def sm(*, model_name: str) -> str:
        return model_name

    async def am(self, *, model_name: str) -> str:
        return model_name


class B(A):
    @classmethod
    def cm(cls, *, model_name: str) -> str:
        return model_name.upper()

    @staticmethod
    def sm(*, model_name: str) -> str:
        return model_name.upper()

    async def am(self, *, model_name: str) -> str:
        return model_name.upper()


async def calls(b: B) -> str:
    return A.cm(model_name="x") + A.sm(model_name="y") + await b.am(model_name="z")
