"""Moved to pkg.d."""
from pkg.moved import raise_moved

raise_moved("pkg.c", "pkg.d", removal="2.0")
