"""Verified renames and moves, and the type-check gate."""

from importlib.metadata import version

from trmv.contract import TRMV

__version__ = version(TRMV.yaml("cli.yaml")["package"])
NATIVE_LANGUAGE = "python"
