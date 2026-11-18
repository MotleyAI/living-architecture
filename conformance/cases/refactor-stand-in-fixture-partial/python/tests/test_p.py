import pytest


class TestBase:
    @pytest.fixture
    def root_model(self) -> str:
        return "x"


class TestSub(TestBase):
    def root_model(self) -> str:
        return "y"
