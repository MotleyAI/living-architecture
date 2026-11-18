from pkg.engine import engine


def test_b(mocker):
    mocker.patch.object(engine, "get_model")
