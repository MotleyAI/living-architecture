import pytest

from pkg.sql.client import Client

docker = pytest.importorskip("docker")
import docker.errors
from pkg.sql.client import X


def test_gated() -> None:
    assert Client.dialect and docker.errors and X
