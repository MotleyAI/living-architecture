import sys
import os
from pkg.database.client import Client
import json
from pkg.sql import dialects


def test_unsorted() -> None:
    assert Client and dialects.D and json and os and sys
