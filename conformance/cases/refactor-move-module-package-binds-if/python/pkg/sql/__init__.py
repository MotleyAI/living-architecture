import os

if os.environ.get("SQL"):
    from . import client
