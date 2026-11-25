from unittest.mock import patch


def test_t() -> None:
    patch("pkg.other.Other.save_model")
    patch("pkg.engine.SearchQueryEngine.save_model")
