import pytest as pt
import pytest_asyncio
from pytest import fixture


class TestA:
    @fixture(scope="module")
    def root_model(self) -> str:
        return "a"


class TestB:
    @pt.fixture
    def root_model(self) -> str:
        return "b"


class TestC:
    @pytest_asyncio.fixture()
    async def root_model(self) -> str:
        return "c"
