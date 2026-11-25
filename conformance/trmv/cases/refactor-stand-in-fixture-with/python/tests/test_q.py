import pytest


class TestQ:
    @pytest.fixture
    def root_model(self) -> str:
        return "x"

    def test_it(self, root_model: str) -> None:
        assert root_model == "x"
